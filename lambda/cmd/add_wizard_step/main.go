package main

import (
	"context"
	"encoding/json"
	"fmt"
	"lambda/models"
	"log"
	"os"
	"time"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/eventbridge"
	"github.com/aws/aws-sdk-go-v2/service/eventbridge/types"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/google/uuid"
)

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	sessionID := request.PathParameters["sessionId"]
	if sessionID == "" {
		return events.APIGatewayProxyResponse{StatusCode: 400}, nil
	}

	var req models.AddWizardStepRequest
	if err := json.Unmarshal([]byte(request.Body), &req); err != nil {
		log.Printf("Error unmarshaling request: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 400}, err
	}

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	ddbClient := dynamodb.NewFromConfig(cfg)
	sqsClient := sqs.NewFromConfig(cfg)
	eventBridgeClient := eventbridge.NewFromConfig(cfg)

	stepID, _ := uuid.NewV7()
	stepIDStr := stepID.String()
	createdAt := time.Now().UTC().Format(time.RFC3339)

	// Get current step count for sort order
	// Query existing steps to determine next sort value

	// Create temporary execution step
	executionStep := models.ExecutionStep{
		PK:                 fmt.Sprintf("EXECUTION#%s", sessionID),
		SK:                 fmt.Sprintf("EXECUTION_STEP#%s", stepIDStr),
		StepID:             stepIDStr,
		Sort:               0, // Will be updated when accepted
		Instruction:        req.Instruction,
		StepType:           req.StepType,
		SecretKey:          req.SecretKey,
		ValidationType:     req.ValidationType,
		ValidationOperator: req.ValidationOperator,
		ValidationValue:    req.ValidationValue,
		CaptureVariable:    req.CaptureVariable,
		AssertionVariable:  req.AssertionVariable,
		ValueType:          req.ValueType,
		CreatedAt:          createdAt,
		AcceptanceStatus:   "pending_acceptance",
		Temporary:          true,
	}

	stepItem, err := attributevalue.MarshalMap(executionStep)
	if err != nil {
		log.Printf("Error marshaling step: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	_, err = ddbClient.PutItem(ctx, &dynamodb.PutItemInput{
		TableName: aws.String(models.GetTableName()),
		Item:      stepItem,
	})
	if err != nil {
		log.Printf("Error creating step: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Send command to EventBridge
	command := map[string]string{
		"action":    "execute_step",
		"sessionId": sessionID,
		"stepId":    stepIDStr,
	}

	commandJSON, _ := json.Marshal(command)
	eventBusName := os.Getenv("WIZARD_EVENT_BUS_NAME")

	if eventBusName != "" {
		// Send to EventBridge (new approach)
		_, err = eventBridgeClient.PutEvents(ctx, &eventbridge.PutEventsInput{
			Entries: []types.PutEventsRequestEntry{
				{
					Source:       aws.String("wizard.commands"),
					DetailType:   aws.String("WizardCommand"),
					Detail:       aws.String(string(commandJSON)),
					EventBusName: aws.String(eventBusName),
				},
			},
		})
		if err != nil {
			log.Printf("Error sending EventBridge event: %v", err)
			return events.APIGatewayProxyResponse{StatusCode: 500}, err
		}
		log.Printf("Command sent to EventBridge for session %s", sessionID)
	} else {
		// Fallback to SQS (legacy approach)
		legacyCommand := models.WizardCommand{
			Action:    "execute_step",
			SessionID: sessionID,
			StepID:    stepIDStr,
		}
		legacyCommandJSON, _ := json.Marshal(legacyCommand)

		_, err = sqsClient.SendMessage(ctx, &sqs.SendMessageInput{
			QueueUrl:    aws.String(os.Getenv("WIZARD_QUEUE_URL")),
			MessageBody: aws.String(string(legacyCommandJSON)),
		})
		if err != nil {
			log.Printf("Error sending SQS message: %v", err)
			return events.APIGatewayProxyResponse{StatusCode: 500}, err
		}
		log.Printf("Command sent to SQS for session %s", sessionID)
	}

	response, _ := json.Marshal(map[string]string{
		"step_id": stepIDStr,
		"status":  "executing",
	})

	return events.APIGatewayProxyResponse{
		StatusCode: 201,
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
