package main

import (
	"context"
	"encoding/json"
	"lambda/models"
	"log"
	"os"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/eventbridge"
	eventbridgetypes "github.com/aws/aws-sdk-go-v2/service/eventbridge/types"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
)

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	sessionID := request.PathParameters["sessionId"]
	if sessionID == "" {
		return events.APIGatewayProxyResponse{StatusCode: 400}, nil
	}

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	sqsClient := sqs.NewFromConfig(cfg)
	eventBridgeClient := eventbridge.NewFromConfig(cfg)

	// Send restart command
	command := map[string]string{
		"action":    "restart",
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
		log.Printf("Restart command sent to EventBridge for session %s", sessionID)
	} else {
		// Fallback to SQS (legacy approach)
		legacyCommand := models.WizardCommand{
			Action:    "restart",
			SessionID: sessionID,
		}
		legacyCommandJSON, _ := json.Marshal(legacyCommand)
		queueURL := os.Getenv("WIZARD_QUEUE_URL")
		messageBody := string(legacyCommandJSON)

		_, err = sqsClient.SendMessage(ctx, &sqs.SendMessageInput{
			QueueUrl:    &queueURL,
			MessageBody: &messageBody,
		})
		if err != nil {
			log.Printf("Error sending SQS message: %v", err)
			return events.APIGatewayProxyResponse{StatusCode: 500}, err
		}
		log.Printf("Restart command sent to SQS for session %s", sessionID)
	}

	response, _ := json.Marshal(map[string]string{
		"status": "restarting",
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
