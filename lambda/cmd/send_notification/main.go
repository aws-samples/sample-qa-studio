package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"

	"lambda/models"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/aws/aws-sdk-go-v2/service/ses"
	sesTypes "github.com/aws/aws-sdk-go-v2/service/ses/types"
)

func handler(ctx context.Context, sqsEvent events.SQSEvent) error {
	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return err
	}

	dynamoClient := dynamodb.NewFromConfig(cfg)
	sesClient := ses.NewFromConfig(cfg)

	for _, record := range sqsEvent.Records {
		var notificationMsg models.NotificationMessage
		err := json.Unmarshal([]byte(record.Body), &notificationMsg)
		if err != nil {
			log.Printf("Error unmarshaling notification message: %v", err)
			continue
		}

		// Get usecase details
		usecase, err := getUsecase(ctx, dynamoClient, notificationMsg.UsecaseID)
		if err != nil {
			log.Printf("Error getting usecase: %v", err)
			continue
		}

		// Get execution details
		execution, err := getExecution(ctx, dynamoClient, notificationMsg.UsecaseID, notificationMsg.ExecutionID)
		if err != nil {
			log.Printf("Error getting execution: %v", err)
			continue
		}

		// Only send to subscribed users for scheduled executions
		if execution.TriggerType == "Scheduled" {
			subscriptions, err := getUserSubscriptions(ctx, dynamoClient, notificationMsg.UsecaseID)
			if err != nil {
				log.Printf("Error getting user subscriptions: %v", err)
			} else {
				for _, subscription := range subscriptions {
					err := sendFailureNotification(ctx, sesClient, subscription.Email, usecase, execution)
					if err != nil {
						log.Printf("Error sending subscription email to %s: %v", subscription.Email, err)
					} else {
						log.Printf("Successfully sent subscription notification to %s", subscription.Email)
					}
				}
			}
		} else {
			log.Printf("Skipping notification for non-scheduled execution (trigger type: %s)", execution.TriggerType)
		}
	}

	return nil
}

func getUsecase(ctx context.Context, client *dynamodb.Client, usecaseID string) (*models.UseCase, error) {
	result, err := client.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: "USECASES"},
			"sk": &types.AttributeValueMemberS{Value: "USECASE#" + usecaseID},
		},
	})
	if err != nil {
		return nil, err
	}

	var usecase models.UseCase
	err = attributevalue.UnmarshalMap(result.Item, &usecase)
	if err != nil {
		return nil, err
	}

	return &usecase, nil
}

func getExecution(ctx context.Context, client *dynamodb.Client, usecaseID, executionID string) (*models.Execution, error) {
	result, err := client.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: "USECASE_EXECUTION#" + usecaseID},
			"sk": &types.AttributeValueMemberS{Value: "EXECUTION#" + executionID},
		},
	})
	if err != nil {
		return nil, err
	}

	var execution models.Execution
	err = attributevalue.UnmarshalMap(result.Item, &execution)
	if err != nil {
		return nil, err
	}

	return &execution, nil
}

func getUserSubscriptions(ctx context.Context, client *dynamodb.Client, usecaseID string) ([]models.UsecaseSubscription, error) {
	input := &dynamodb.QueryInput{
		TableName:              aws.String(models.GetTableName()),
		KeyConditionExpression: aws.String("pk = :pk AND begins_with(sk, :sk)"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":pk": &types.AttributeValueMemberS{Value: "USECASE#" + usecaseID},
			":sk": &types.AttributeValueMemberS{Value: "NOTIFICATION#"},
		},
	}

	result, err := client.Query(ctx, input)
	if err != nil {
		return nil, err
	}

	var subscriptions []models.UsecaseSubscription
	err = attributevalue.UnmarshalListOfMaps(result.Items, &subscriptions)
	if err != nil {
		return nil, err
	}

	return subscriptions, nil
}

func sendFailureNotification(ctx context.Context, sesClient *ses.Client, recipientEmail string, usecase *models.UseCase, execution *models.Execution) error {
	subject := fmt.Sprintf("Execution Failed: %s", usecase.Name)

	htmlBody := fmt.Sprintf(`
		<html>
		<body>
			<h2>Execution Failed</h2>
			<p><strong>Usecase:</strong> %s</p>
			<p><strong>Description:</strong> %s</p>
			<p><strong>Execution ID:</strong> %s</p>
			<p><strong>Status:</strong> %s</p>
			<p><strong>Trigger Type:</strong> %s</p>
			<p><strong>Started At:</strong> %s</p>
			<p><strong>Completed At:</strong> %s</p>
			<p><strong>Starting URL:</strong> %s</p>
		</body>
		</html>
	`, usecase.Name, usecase.Description, execution.SK[10:], execution.Status, execution.TriggerType, execution.CreatedAt, execution.CompletedAt, execution.StartingURL)

	textBody := fmt.Sprintf(`
Execution Failed

Usecase: %s
Description: %s
Execution ID: %s
Status: %s
Trigger Type: %s
Started At: %s
Completed At: %s
Starting URL: %s
	`, usecase.Name, usecase.Description, execution.SK[10:], execution.Status, execution.TriggerType, execution.CreatedAt, execution.CompletedAt, execution.StartingURL)

	input := &ses.SendEmailInput{
		Source: aws.String("noreply@example.com"), // This should be configured with a verified SES email
		Destination: &sesTypes.Destination{
			ToAddresses: []string{recipientEmail},
		},
		Message: &sesTypes.Message{
			Subject: &sesTypes.Content{
				Data: aws.String(subject),
			},
			Body: &sesTypes.Body{
				Html: &sesTypes.Content{
					Data: aws.String(htmlBody),
				},
				Text: &sesTypes.Content{
					Data: aws.String(textBody),
				},
			},
		},
	}

	_, err := sesClient.SendEmail(ctx, input)
	return err
}

func main() {
	lambda.Start(handler)
}
