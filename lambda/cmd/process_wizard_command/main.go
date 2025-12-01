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
	"github.com/google/uuid"
)

// WizardCommand represents a command from EventBridge
type WizardCommand struct {
	Action    string `json:"action"`
	SessionID string `json:"sessionId"`
	StepID    string `json:"stepId,omitempty"`
}

// CommandRecord represents a command stored in DynamoDB
type CommandRecord struct {
	PK        string `json:"pk" dynamodbav:"pk"`
	SK        string `json:"sk" dynamodbav:"sk"`
	CommandID string `json:"commandId" dynamodbav:"command_id"`
	Action    string `json:"action" dynamodbav:"action"`
	SessionID string `json:"sessionId" dynamodbav:"session_id"`
	StepID    string `json:"stepId,omitempty" dynamodbav:"step_id,omitempty"`
	CreatedAt string `json:"createdAt" dynamodbav:"created_at"`
	TTL       int64  `json:"ttl" dynamodbav:"ttl"` // Auto-delete after 1 hour
}

func handler(ctx context.Context, event events.CloudWatchEvent) error {
	log.Printf("Received EventBridge event: %s", event.DetailType)

	// Parse the command from event detail
	var command WizardCommand
	err := json.Unmarshal(event.Detail, &command)
	if err != nil {
		log.Printf("Error unmarshaling command: %v", err)
		return err
	}

	log.Printf("Processing command: %s for session: %s", command.Action, command.SessionID)

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return err
	}

	ddbClient := dynamodb.NewFromConfig(cfg)

	// Create command record
	commandID, _ := uuid.NewV7()
	now := time.Now().UTC()

	commandRecord := CommandRecord{
		PK:        fmt.Sprintf("WIZARD_COMMAND#%s", command.SessionID),
		SK:        fmt.Sprintf("COMMAND#%s#%s", now.Format("20060102150405.000000"), commandID.String()),
		CommandID: commandID.String(),
		Action:    command.Action,
		SessionID: command.SessionID,
		StepID:    command.StepID,
		CreatedAt: now.Format(time.RFC3339),
		TTL:       now.Add(1 * time.Hour).Unix(), // Auto-delete after 1 hour
	}

	item, err := attributevalue.MarshalMap(commandRecord)
	if err != nil {
		log.Printf("Error marshaling command: %v", err)
		return err
	}

	// Write to DynamoDB
	_, err = ddbClient.PutItem(ctx, &dynamodb.PutItemInput{
		TableName: aws.String(models.GetTableName()),
		Item:      item,
	})
	if err != nil {
		log.Printf("Error writing command to DynamoDB: %v", err)
		return err
	}

	log.Printf("Command %s written to DynamoDB for session %s", commandID.String(), command.SessionID)
	return nil
}

func main() {
	lambda.Start(handler)
}
