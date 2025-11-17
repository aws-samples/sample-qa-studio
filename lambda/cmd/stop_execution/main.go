package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"time"

	"lambda/models"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/aws/aws-sdk-go-v2/service/ecs"
)

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	executionId := request.PathParameters["executionId"]
	usecaseId := request.PathParameters["id"]
	if executionId == "" || usecaseId == "" {
		return events.APIGatewayProxyResponse{
			StatusCode: 400,
			Headers: map[string]string{
				"Content-Type":                 "application/json",
				"Access-Control-Allow-Origin":  "*",
				"Access-Control-Allow-Methods": "POST, OPTIONS",
				"Access-Control-Allow-Headers": "Content-Type, Authorization",
			},
			Body: `{"error": "missing executionId or usecaseId"}`,
		}, nil
	}

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	ddbClient := dynamodb.NewFromConfig(cfg)

	// Load execution to get task ARN
	result, err := ddbClient.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE_EXECUTION#%s", usecaseId)},
			"sk": &types.AttributeValueMemberS{Value: fmt.Sprintf("EXECUTION#%s", executionId)},
		},
	})
	if err != nil {
		log.Printf("Error getting execution: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	if result.Item == nil {
		return events.APIGatewayProxyResponse{
			StatusCode: 404,
			Headers: map[string]string{
				"Content-Type":                 "application/json",
				"Access-Control-Allow-Origin":  "*",
				"Access-Control-Allow-Methods": "POST, OPTIONS",
				"Access-Control-Allow-Headers": "Content-Type, Authorization",
			},
			Body: `{"error": "execution not found"}`,
		}, nil
	}

	var execution models.Execution
	err = attributevalue.UnmarshalMap(result.Item, &execution)
	if err != nil {
		log.Printf("Error unmarshaling execution: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Check if execution has a task ARN
	if execution.TaskArn == "" {
		return events.APIGatewayProxyResponse{
			StatusCode: 400,
			Headers: map[string]string{
				"Content-Type":                 "application/json",
				"Access-Control-Allow-Origin":  "*",
				"Access-Control-Allow-Methods": "POST, OPTIONS",
				"Access-Control-Allow-Headers": "Content-Type, Authorization",
			},
			Body: `{"error": "execution has no associated ECS task"}`,
		}, nil
	}

	// Check if execution is already in a terminal state
	if execution.Status == "success" || execution.Status == "failed" || execution.Status == "stopped" || execution.Status == "error" {
		return events.APIGatewayProxyResponse{
			StatusCode: 400,
			Headers: map[string]string{
				"Content-Type":                 "application/json",
				"Access-Control-Allow-Origin":  "*",
				"Access-Control-Allow-Methods": "POST, OPTIONS",
				"Access-Control-Allow-Headers": "Content-Type, Authorization",
			},
			Body: fmt.Sprintf(`{"error": "execution is already in terminal state: %s"}`, execution.Status),
		}, nil
	}

	// Stop the ECS task
	ecsClient := ecs.NewFromConfig(cfg)
	clusterArn := os.Getenv("ECS_CLUSTER")

	log.Printf("Stopping ECS task: %s in cluster: %s", execution.TaskArn, clusterArn)

	_, err = ecsClient.StopTask(ctx, &ecs.StopTaskInput{
		Cluster: aws.String(clusterArn),
		Task:    aws.String(execution.TaskArn),
		Reason:  aws.String("User requested stop via API"),
	})
	if err != nil {
		log.Printf("Error stopping ECS task: %v", err)
		// Don't fail completely - update status anyway
		// The task might already be stopped or not exist
		log.Printf("Warning: Failed to stop task, but will update execution status anyway")
	} else {
		log.Printf("Successfully stopped ECS task: %s", execution.TaskArn)
	}

	// Update execution status to stopped
	completedAt := time.Now().UTC().Format(time.RFC3339)
	_, err = ddbClient.UpdateItem(ctx, &dynamodb.UpdateItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE_EXECUTION#%s", usecaseId)},
			"sk": &types.AttributeValueMemberS{Value: fmt.Sprintf("EXECUTION#%s", executionId)},
		},
		UpdateExpression: aws.String("SET #status = :status, completed_at = :completed_at"),
		ExpressionAttributeNames: map[string]string{
			"#status": "status",
		},
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":status":       &types.AttributeValueMemberS{Value: "stopped"},
			":completed_at": &types.AttributeValueMemberS{Value: completedAt},
		},
	})
	if err != nil {
		log.Printf("Error updating execution status: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	log.Printf("Updated execution %s status to stopped", executionId)

	response, err := json.Marshal(map[string]interface{}{
		"status":      "stopped",
		"executionId": executionId,
		"taskArn":     execution.TaskArn,
		"stoppedAt":   completedAt,
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
			"Access-Control-Allow-Methods": "POST, OPTIONS",
			"Access-Control-Allow-Headers": "Content-Type, Authorization",
		},
		Body: string(response),
	}, nil
}

func main() {
	lambda.Start(handler)
}
