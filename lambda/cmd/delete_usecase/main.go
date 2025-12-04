package main

import (
	"context"
	"encoding/json"
	"fmt"
	"lambda/models"
	"log"
	"regexp"
	"strings"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/aws/aws-sdk-go-v2/service/novaact"
)

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	usecaseId := request.PathParameters["id"]
	if usecaseId == "" {
		return events.APIGatewayProxyResponse{StatusCode: 400}, nil
	}

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	client := dynamodb.NewFromConfig(cfg)

	// Delete Nova Act workflow definition if it exists
	deleteWorkflowDefinition(ctx, usecaseId)

	// Delete usecase metadata
	_, err = client.DeleteItem(ctx, &dynamodb.DeleteItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: "USECASES"},
			"sk": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE#%s", usecaseId)},
		},
	})
	if err != nil {
		log.Printf("Error deleting usecase: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Delete CREATED_BY record (if it exists)
	_, err = client.DeleteItem(ctx, &dynamodb.DeleteItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE#%s", usecaseId)},
			"sk": &types.AttributeValueMemberS{Value: "CREATED_BY"},
		},
	})
	if err != nil {
		log.Printf("Error deleting created_by record (may not exist for older usecases): %v", err)
		// Don't return error here as the record might not exist for older usecases
	}

	// Query and delete all steps
	stepsResult, err := client.Query(ctx, &dynamodb.QueryInput{
		TableName:              aws.String(models.GetTableName()),
		KeyConditionExpression: aws.String("pk = :usecaseId AND begins_with(sk, :prefix)"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":usecaseId": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE#%s", usecaseId)},
			":prefix":    &types.AttributeValueMemberS{Value: "STEP#"},
		},
	})
	if err != nil {
		log.Printf("Error querying steps: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	for _, item := range stepsResult.Items {
		_, err = client.DeleteItem(ctx, &dynamodb.DeleteItemInput{
			TableName: aws.String(models.GetTableName()),
			Key: map[string]types.AttributeValue{
				"pk": item["pk"],
				"sk": item["sk"],
			},
		})
		if err != nil {
			log.Printf("Error deleting step: %v", err)
		}
	}

	// Query and delete all executions
	executionsResult, err := client.Query(ctx, &dynamodb.QueryInput{
		TableName:              aws.String(models.GetTableName()),
		KeyConditionExpression: aws.String("pk = :usecaseId AND begins_with(sk, :prefix)"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":usecaseId": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE_EXECUTION#%s", usecaseId)},
			":prefix":    &types.AttributeValueMemberS{Value: "EXECUTION#"},
		},
	})
	if err != nil {
		log.Printf("Error querying executions: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	for _, item := range executionsResult.Items {
		executionId := item["pk"]

		// Delete execution
		_, err = client.DeleteItem(ctx, &dynamodb.DeleteItemInput{
			TableName: aws.String(models.GetTableName()),
			Key: map[string]types.AttributeValue{
				"pk": executionId,
				"sk": item["sk"],
			},
		})
		if err != nil {
			log.Printf("Error deleting execution: %v", err)
		}

		// Query and delete execution steps
		var executionIdStr string
		attributevalue.Unmarshal(executionId, &executionIdStr)

		executionStepsResult, err := client.Query(ctx, &dynamodb.QueryInput{
			TableName:              aws.String(models.GetTableName()),
			KeyConditionExpression: aws.String("pk = :executionId AND begins_with(sk, :prefix)"),
			ExpressionAttributeValues: map[string]types.AttributeValue{
				":executionId": &types.AttributeValueMemberS{Value: fmt.Sprintf("EXECUTION#%s", executionIdStr)},
				":prefix":      &types.AttributeValueMemberS{Value: "EXECUTION_STEP#"},
			},
		})
		if err != nil {
			log.Printf("Error querying execution steps: %v", err)
			continue
		}

		for _, stepItem := range executionStepsResult.Items {
			_, err = client.DeleteItem(ctx, &dynamodb.DeleteItemInput{
				TableName: aws.String(models.GetTableName()),
				Key: map[string]types.AttributeValue{
					"pk": stepItem["pk"],
					"sk": stepItem["sk"],
				},
			})
			if err != nil {
				log.Printf("Error deleting execution step: %v", err)
			}
		}
	}

	response, err := json.Marshal(map[string]string{
		"status":    "usecase deleted",
		"usecaseId": usecaseId,
	})
	if err != nil {
		log.Printf("Error marshaling response: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	return events.APIGatewayProxyResponse{
		StatusCode: 200,
		Headers: map[string]string{
			"Content-Type":                 "application/json",
			"Access-Control-Allow-Origin":  "*",
			"Access-Control-Allow-Methods": "DELETE, OPTIONS",
			"Access-Control-Allow-Headers": "Content-Type, Authorization",
		},
		Body: string(response),
	}, nil
}

func deleteWorkflowDefinition(ctx context.Context, usecaseId string) {
	// Sanitize workflow name to match Python logic
	// Workflow names: 1-40 chars, a-z A-Z 0-9 - _, no spaces
	reg := regexp.MustCompile(`[^a-zA-Z0-9\-_]`)
	workflowName := reg.ReplaceAllString(usecaseId, "-")

	// Ensure max 40 chars
	if len(workflowName) > 40 {
		workflowName = workflowName[:40]
	}

	// Create Nova Act client in us-east-1 (GA region)
	cfg, err := config.LoadDefaultConfig(ctx, config.WithRegion("us-east-1"))
	if err != nil {
		log.Printf("Warning: Could not load config for Nova Act client: %v", err)
		return
	}

	novaActClient := novaact.NewFromConfig(cfg)

	// Try to delete the workflow definition
	_, err = novaActClient.DeleteWorkflowDefinition(ctx, &novaact.DeleteWorkflowDefinitionInput{
		WorkflowDefinitionName: aws.String(workflowName),
	})

	if err != nil {
		// Check if it's a ResourceNotFoundException (workflow doesn't exist)
		if strings.Contains(err.Error(), "ResourceNotFoundException") {
			log.Printf("Workflow definition '%s' does not exist, nothing to delete", workflowName)
		} else {
			log.Printf("Warning: Could not delete workflow definition '%s': %v", workflowName, err)
		}
	} else {
		log.Printf("Successfully deleted workflow definition '%s' for usecase %s", workflowName, usecaseId)
	}
}

func main() {
	lambda.Start(handler)
}
