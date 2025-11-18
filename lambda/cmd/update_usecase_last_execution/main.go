package main

import (
	"context"
	"encoding/json"
	"fmt"
	"lambda/models"
	"log"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

type ExecutionStatusChangedEvent struct {
	UsecaseID   string `json:"usecase_id"`
	ExecutionID string `json:"execution_id"`
	Status      string `json:"status"`
	Timestamp   string `json:"timestamp"`
	CompletedAt string `json:"completed_at,omitempty"`
}

func handler(ctx context.Context, event events.CloudWatchEvent) error {
	log.Printf("Received event: %s from source: %s", event.DetailType, event.Source)

	// Parse the event detail
	var statusEvent ExecutionStatusChangedEvent
	err := json.Unmarshal(event.Detail, &statusEvent)
	if err != nil {
		log.Printf("Error unmarshaling event detail: %v", err)
		return err
	}

	log.Printf("Processing status change: usecase=%s, execution=%s, status=%s",
		statusEvent.UsecaseID, statusEvent.ExecutionID, statusEvent.Status)

	// Initialize AWS SDK
	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return err
	}

	client := dynamodb.NewFromConfig(cfg)
	tableName := models.GetTableName()

	// Update the usecase record with latest execution info
	updateExpression := "SET last_execution_id = :exec_id, last_execution_status = :status, last_execution_time = :timestamp"
	expressionAttributeValues := map[string]types.AttributeValue{
		":exec_id":   &types.AttributeValueMemberS{Value: statusEvent.ExecutionID},
		":status":    &types.AttributeValueMemberS{Value: statusEvent.Status},
		":timestamp": &types.AttributeValueMemberS{Value: statusEvent.Timestamp},
	}

	_, err = client.UpdateItem(ctx, &dynamodb.UpdateItemInput{
		TableName: aws.String(tableName),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: "USECASES"},
			"sk": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE#%s", statusEvent.UsecaseID)},
		},
		UpdateExpression:          aws.String(updateExpression),
		ExpressionAttributeValues: expressionAttributeValues,
	})

	if err != nil {
		log.Printf("Error updating usecase last execution: %v", err)
		return err
	}

	log.Printf("Successfully updated usecase %s with latest execution info", statusEvent.UsecaseID)
	return nil
}

func main() {
	lambda.Start(handler)
}
