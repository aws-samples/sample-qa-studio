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
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/aws/aws-sdk-go-v2/service/eventbridge"
	eventbridgetypes "github.com/aws/aws-sdk-go-v2/service/eventbridge/types"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
)

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	sessionID := request.PathParameters["sessionId"]
	usecaseID := request.PathParameters["usecaseId"]

	if sessionID == "" || usecaseID == "" {
		return events.APIGatewayProxyResponse{StatusCode: 400}, nil
	}

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	ddbClient := dynamodb.NewFromConfig(cfg)
	sqsClient := sqs.NewFromConfig(cfg)
	eventBridgeClient := eventbridge.NewFromConfig(cfg)

	// Update execution status
	_, err = ddbClient.UpdateItem(ctx, &dynamodb.UpdateItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE_EXECUTION#%s", usecaseID)},
			"sk": &types.AttributeValueMemberS{Value: fmt.Sprintf("EXECUTION#%s", sessionID)},
		},
		UpdateExpression: aws.String("SET wizard_status = :status, completed_at = :completed"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":status":    &types.AttributeValueMemberS{Value: "closed"},
			":completed": &types.AttributeValueMemberS{Value: time.Now().UTC().Format(time.RFC3339)},
		},
	})
	if err != nil {
		log.Printf("Error updating execution: %v", err)
	}

	// Send terminate command for graceful shutdown
	command := map[string]string{
		"action":    "terminate",
		"sessionId": sessionID,
	}

	commandJSON, _ := json.Marshal(command)
	eventBusName := os.Getenv("WIZARD_EVENT_BUS_NAME")

	if eventBusName != "" {
		// Send to EventBridge (new approach)
		_, err = eventBridgeClient.PutEvents(ctx, &eventbridge.PutEventsInput{
			Entries: []eventbridgetypes.PutEventsRequestEntry{
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
		log.Printf("Terminate command sent to EventBridge for session %s", sessionID)
	} else {
		// Fallback to SQS (legacy approach)
		legacyCommand := models.WizardCommand{
			Action:    "terminate",
			SessionID: sessionID,
		}
		legacyCommandJSON, _ := json.Marshal(legacyCommand)

		_, err = sqsClient.SendMessage(ctx, &sqs.SendMessageInput{
			QueueUrl:    aws.String(os.Getenv("WIZARD_QUEUE_URL")),
			MessageBody: aws.String(string(legacyCommandJSON)),
		})
		if err != nil {
			log.Printf("Error sending terminate command to SQS: %v", err)
			return events.APIGatewayProxyResponse{StatusCode: 500}, err
		}
		log.Printf("Terminate command sent to SQS for session %s", sessionID)
	}

	response, _ := json.Marshal(map[string]string{
		"status": "terminated",
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
