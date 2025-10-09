package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"

	"lambda/models"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/aws/aws-sdk-go-v2/service/sns"
	snsTypes "github.com/aws/aws-sdk-go-v2/service/sns/types"
)

func handler(ctx context.Context, sqsEvent events.SQSEvent) error {
	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return err
	}

	dynamoClient := dynamodb.NewFromConfig(cfg)
	snsClient := sns.NewFromConfig(cfg)

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

		// Check if we should send notifications for this execution
		shouldNotify := shouldSendNotification(execution)
		if !shouldNotify {
			log.Printf("Skipping notification for execution (trigger type: %s, status: %s)", execution.TriggerType, execution.Status)
			continue
		}

		// Get subscribed users for this usecase
		subscriptions, err := getUserSubscriptions(ctx, dynamoClient, notificationMsg.UsecaseID)
		if err != nil {
			log.Printf("Error getting user subscriptions: %v", err)
			continue
		}

		if len(subscriptions) == 0 {
			log.Printf("No subscriptions found for usecase %s", notificationMsg.UsecaseID)
			continue
		}

		// Send SNS notification with usecase_id filter attribute
		// SNS will automatically filter to only subscribed users for this usecase
		err = sendSNSNotificationWithFilter(ctx, snsClient, usecase, execution)
		if err != nil {
			log.Printf("Error sending SNS notification for usecase %s: %v", usecase.Name, err)
		} else {
			log.Printf("Successfully sent SNS notification for usecase %s to %d subscribers", usecase.Name, len(subscriptions))
		}
	}

	return nil
}

// shouldSendNotification determines if we should send a notification based on execution details
func shouldSendNotification(execution *models.Execution) bool {
	// Send notifications for:
	// 1. Scheduled executions that failed
	// 2. Any execution that failed (optional - you can customize this logic)

	// For now, let's send notifications for failed executions
	if execution.TriggerType == "Scheduled" && execution.Status == "error" {
		return true
	}

	return false
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

func sendSNSNotificationWithFilter(ctx context.Context, snsClient *sns.Client, usecase *models.UseCase, execution *models.Execution) error {
	// Get SNS topic ARN from environment variable
	topicArn := os.Getenv("SNS_TOPIC_ARN")
	if topicArn == "" {
		return fmt.Errorf("SNS_TOPIC_ARN environment variable not set")
	}

	// Get frontend URL from environment variable
	frontendUrl := os.Getenv("FRONTEND_URL")
	if frontendUrl == "" {
		frontendUrl = "https://your-app.com" // Default fallback
	}

	// Create notification subject and status emoji based on execution status
	var subject, statusEmoji, statusMessage string
	switch execution.Status {
	case "COMPLETED":
		subject = fmt.Sprintf("✅ Execution Completed: %s", usecase.Name)
		statusEmoji = "✅"
		statusMessage = "Your usecase execution completed successfully!"
	case "FAILED", "ERROR":
		subject = fmt.Sprintf("❌ Execution Failed: %s", usecase.Name)
		statusEmoji = "❌"
		statusMessage = "Your usecase execution encountered an error and failed."
	default:
		subject = fmt.Sprintf("📋 Execution Update: %s", usecase.Name)
		statusEmoji = "📋"
		statusMessage = fmt.Sprintf("Your usecase execution status: %s", execution.Status)
	}

	// Create execution link
	executionId := getExecutionID(execution.SK)
	executionLink := fmt.Sprintf("%s/usecase/%s/execution/%s", frontendUrl, usecase.ID, executionId)

	// Create rich notification message with execution link
	message := fmt.Sprintf(`
%s %s

%s

📋 EXECUTION DETAILS:
• Usecase: %s
• Description: %s
• Execution ID: %s
• Status: %s %s
• Trigger Type: %s
• Started At: %s
• Completed At: %s
• Starting URL: %s

🔗 VIEW FULL DETAILS: %s

---
To manage your subscriptions, visit your dashboard.
	`, statusEmoji, usecase.Name, statusMessage, usecase.Name, usecase.Description, executionId, execution.Status, statusEmoji, execution.TriggerType, execution.CreatedAt, execution.CompletedAt, execution.StartingURL, executionLink)

	// Create message attributes for SNS filtering
	// The key attribute is usecase_id which will be used for filtering
	messageAttributes := map[string]snsTypes.MessageAttributeValue{
		"usecase_id": {
			DataType:    aws.String("String"),
			StringValue: aws.String(usecase.ID),
		},
		"execution_status": {
			DataType:    aws.String("String"),
			StringValue: aws.String(execution.Status),
		},
		"trigger_type": {
			DataType:    aws.String("String"),
			StringValue: aws.String(execution.TriggerType),
		},
	}

	// Publish to SNS topic with filter attributes
	input := &sns.PublishInput{
		TopicArn:          aws.String(topicArn),
		Subject:           aws.String(subject),
		Message:           aws.String(message),
		MessageAttributes: messageAttributes,
	}

	result, err := snsClient.Publish(ctx, input)
	if err != nil {
		return fmt.Errorf("failed to publish SNS message: %w", err)
	}

	log.Printf("Published SNS message %s for usecase %s with filter usecase_id=%s", aws.ToString(result.MessageId), usecase.Name, usecase.ID)
	return nil
}

// getExecutionID extracts execution ID from SK (removes "EXECUTION#" prefix)
func getExecutionID(sk string) string {
	if len(sk) > 10 && sk[:10] == "EXECUTION#" {
		return sk[10:]
	}
	return sk
}

func main() {
	lambda.Start(handler)
}
