package main

import (
	"context"
	"encoding/json"
	"fmt"
	"lambda/models"
	"log"
	"time"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/google/uuid"
)

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	sessionID := request.PathParameters["sessionId"]
	stepID := request.PathParameters["stepId"]
	usecaseID := request.PathParameters["usecaseId"]

	if sessionID == "" || stepID == "" || usecaseID == "" {
		return events.APIGatewayProxyResponse{StatusCode: 400}, nil
	}

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	ddbClient := dynamodb.NewFromConfig(cfg)

	// Get the execution step
	result, err := ddbClient.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: fmt.Sprintf("EXECUTION#%s", sessionID)},
			"sk": &types.AttributeValueMemberS{Value: fmt.Sprintf("EXECUTION_STEP#%s", stepID)},
		},
	})
	if err != nil || result.Item == nil {
		log.Printf("Error getting step: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 404}, err
	}

	var executionStep models.ExecutionStep
	err = attributevalue.UnmarshalMap(result.Item, &executionStep)
	if err != nil {
		log.Printf("Error unmarshaling step: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Count existing accepted steps to determine sort order
	queryResult, err := ddbClient.Query(ctx, &dynamodb.QueryInput{
		TableName:              aws.String(models.GetTableName()),
		KeyConditionExpression: aws.String("pk = :pk AND begins_with(sk, :sk)"),
		FilterExpression:       aws.String("acceptance_status = :status"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":pk":     &types.AttributeValueMemberS{Value: fmt.Sprintf("EXECUTION#%s", sessionID)},
			":sk":     &types.AttributeValueMemberS{Value: "EXECUTION_STEP#"},
			":status": &types.AttributeValueMemberS{Value: "accepted"},
		},
	})
	if err != nil {
		log.Printf("Error querying steps: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	nextSort := len(queryResult.Items)

	// Update execution step to accepted
	_, err = ddbClient.UpdateItem(ctx, &dynamodb.UpdateItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: fmt.Sprintf("EXECUTION#%s", sessionID)},
			"sk": &types.AttributeValueMemberS{Value: fmt.Sprintf("EXECUTION_STEP#%s", stepID)},
		},
		UpdateExpression: aws.String("SET acceptance_status = :status, #temp = :temp, sort = :sort"),
		ExpressionAttributeNames: map[string]string{
			"#temp": "temporary",
		},
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":status": &types.AttributeValueMemberS{Value: "accepted"},
			":temp":   &types.AttributeValueMemberBOOL{Value: false},
			":sort":   &types.AttributeValueMemberN{Value: fmt.Sprintf("%d", nextSort)},
		},
	})
	if err != nil {
		log.Printf("Error updating step: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Create permanent step in use case
	permanentStepID, _ := uuid.NewV7()
	permanentStep := models.Step{
		PK:                 fmt.Sprintf("USECASE#%s", usecaseID),
		SK:                 fmt.Sprintf("STEP#%s", permanentStepID.String()),
		ID:                 permanentStepID.String(),
		Sort:               nextSort,
		Instruction:        executionStep.Instruction,
		StepType:           executionStep.StepType,
		SecretKey:          executionStep.SecretKey,
		ValidationType:     executionStep.ValidationType,
		ValidationOperator: executionStep.ValidationOperator,
		ValidationValue:    executionStep.ValidationValue,
		CaptureVariable:    executionStep.CaptureVariable,
		AssertionVariable:  executionStep.AssertionVariable,
		ValueType:          executionStep.ValueType,
		CreatedAt:          time.Now().UTC().Format(time.RFC3339),
	}

	permanentStepItem, err := attributevalue.MarshalMap(permanentStep)
	if err != nil {
		log.Printf("Error marshaling permanent step: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	_, err = ddbClient.PutItem(ctx, &dynamodb.PutItemInput{
		TableName: aws.String(models.GetTableName()),
		Item:      permanentStepItem,
	})
	if err != nil {
		log.Printf("Error creating permanent step: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	response, _ := json.Marshal(map[string]string{
		"status":  "accepted",
		"step_id": permanentStep.ID,
	})

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
