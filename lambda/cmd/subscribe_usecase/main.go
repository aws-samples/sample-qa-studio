package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strings"
	"time"

	"lambda/models"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/aws/aws-sdk-go-v2/service/sns"
	"github.com/google/uuid"
)

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	usecaseId := request.PathParameters["id"]
	if usecaseId == "" {
		return events.APIGatewayProxyResponse{StatusCode: 400}, nil
	}

	// Extract user email from JWT token claims
	userEmail := ""
	if claims, ok := request.RequestContext.Authorizer["claims"].(map[string]interface{}); ok {
		if email, exists := claims["email"].(string); exists {
			userEmail = email
		}
	}

	if userEmail == "" {
		log.Printf("No email found in JWT claims")
		return events.APIGatewayProxyResponse{StatusCode: 401}, nil
	}

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	dynamoClient := dynamodb.NewFromConfig(cfg)
	snsClient := sns.NewFromConfig(cfg)

	// Create subscription record first
	// (We need this in DynamoDB before updating SNS filter policy)
	subscription := models.UsecaseSubscription{
		PK:        "USECASE#" + usecaseId,
		SK:        "NOTIFICATION#" + uuid.New().String(),
		Email:     userEmail,
		CreatedAt: time.Now().UTC().Format(time.RFC3339),
	}

	item, err := attributevalue.MarshalMap(subscription)
	if err != nil {
		log.Printf("Error marshaling item: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	_, err = dynamoClient.PutItem(ctx, &dynamodb.PutItemInput{
		TableName: aws.String(models.GetTableName()),
		Item:      item,
	})
	if err != nil {
		log.Printf("Error putting item: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Now subscribe user to SNS topic and set/update filter policy for this usecase
	err = ensureSNSSubscriptionWithFilter(ctx, snsClient, dynamoClient, userEmail, usecaseId)
	if err != nil {
		log.Printf("Error ensuring SNS subscription with filter: %v", err)
		// Continue anyway - don't fail the usecase subscription
	}

	// Return subscription status (should be true after subscribing)
	response := models.SubscriptionStatusResponse{
		IsSubscribed: true,
		Email:        userEmail,
	}

	body, err := json.Marshal(response)
	if err != nil {
		log.Printf("Error marshaling response: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	return events.APIGatewayProxyResponse{
		StatusCode: 201,
		Headers: map[string]string{
			"Content-Type":                 "application/json",
			"Access-Control-Allow-Origin":  "*",
			"Access-Control-Allow-Methods": "POST, OPTIONS",
			"Access-Control-Allow-Headers": "Content-Type, Authorization",
		},
		Body: string(body),
	}, nil
}

// ensureSNSSubscriptionWithFilter subscribes the user to SNS topic and sets/updates filter policy
func ensureSNSSubscriptionWithFilter(ctx context.Context, snsClient *sns.Client, dynamoClient *dynamodb.Client, email, usecaseId string) error {
	topicArn := os.Getenv("SNS_TOPIC_ARN")
	if topicArn == "" {
		return nil // Skip if no topic configured
	}

	// Check if user is already subscribed by listing subscriptions
	listInput := &sns.ListSubscriptionsByTopicInput{
		TopicArn: aws.String(topicArn),
	}

	result, err := snsClient.ListSubscriptionsByTopic(ctx, listInput)
	if err != nil {
		log.Printf("Error listing SNS subscriptions: %v", err)
		return err
	}

	var subscriptionArn string
	var existingSubscription bool

	// Check if email is already subscribed
	for _, subscription := range result.Subscriptions {
		if aws.ToString(subscription.Endpoint) == email && aws.ToString(subscription.Protocol) == "email" {
			subscriptionArn = aws.ToString(subscription.SubscriptionArn)
			existingSubscription = true
			log.Printf("User %s already subscribed to SNS topic with ARN: %s", email, subscriptionArn)
			break
		}
	}

	// If not subscribed, subscribe them first with initial filter policy
	if !existingSubscription {
		// Create initial filter policy for this usecase
		initialFilterPolicy := createFilterPolicyJSON([]string{usecaseId})

		subscribeInput := &sns.SubscribeInput{
			TopicArn: aws.String(topicArn),
			Protocol: aws.String("email"),
			Endpoint: aws.String(email),
			Attributes: map[string]string{
				"FilterPolicy": initialFilterPolicy,
			},
		}

		subscribeResult, err := snsClient.Subscribe(ctx, subscribeInput)
		if err != nil {
			log.Printf("Error subscribing %s to SNS topic: %v", email, err)
			return err
		}

		subscriptionArn = aws.ToString(subscribeResult.SubscriptionArn)
		log.Printf("Successfully subscribed %s to SNS topic with filter policy %s. Subscription ARN: %s", email, initialFilterPolicy, subscriptionArn)
	} else {
		// For existing subscriptions, update the filter policy to include the new usecase
		if subscriptionArn != "" && subscriptionArn != "PendingConfirmation" {
			err = updateFilterPolicyForUser(ctx, snsClient, dynamoClient, email, usecaseId)
			if err != nil {
				log.Printf("Warning: Could not update filter policy for %s: %v", email, err)
			} else {
				log.Printf("Successfully updated filter policy for existing subscriber %s", email)
			}
		} else {
			log.Printf("Subscription pending confirmation for %s - filter policy will be updated after confirmation", email)
		}
	}

	return nil
}

// updateFilterPolicyForUser finds the user's subscription and updates their filter policy
func updateFilterPolicyForUser(ctx context.Context, snsClient *sns.Client, dynamoClient *dynamodb.Client, email, usecaseId string) error {
	topicArn := os.Getenv("SNS_TOPIC_ARN")
	if topicArn == "" {
		return fmt.Errorf("SNS_TOPIC_ARN not set")
	}

	// Find the user's subscription
	listInput := &sns.ListSubscriptionsByTopicInput{
		TopicArn: aws.String(topicArn),
	}

	result, err := snsClient.ListSubscriptionsByTopic(ctx, listInput)
	if err != nil {
		return fmt.Errorf("failed to list subscriptions: %w", err)
	}

	var subscriptionArn string
	for _, subscription := range result.Subscriptions {
		if aws.ToString(subscription.Endpoint) == email &&
			aws.ToString(subscription.Protocol) == "email" &&
			aws.ToString(subscription.SubscriptionArn) != "PendingConfirmation" {
			subscriptionArn = aws.ToString(subscription.SubscriptionArn)
			break
		}
	}

	if subscriptionArn == "" {
		return fmt.Errorf("no confirmed subscription found for %s", email)
	}

	// Get current filter policy from SNS subscription (ONLY source of truth)
	// We ignore DynamoDB state and work purely with what's in the SNS filter policy
	currentUsecases, err := getCurrentFilterPolicyUsecases(ctx, snsClient, subscriptionArn)
	if err != nil {
		log.Printf("Warning: Could not get current filter policy, starting fresh: %v", err)
		currentUsecases = []string{}
	}

	log.Printf("Current SNS filter policy usecases for %s: %v", email, currentUsecases)

	// Add the new usecase if not already in the list
	found := false
	for _, id := range currentUsecases {
		if id == usecaseId {
			found = true
			break
		}
	}
	if !found {
		currentUsecases = append(currentUsecases, usecaseId)
	}

	// Create filter policy JSON with updated usecases
	filterPolicy := createFilterPolicyJSON(currentUsecases)
	log.Printf("Setting filter policy for %s with usecases %v: %s", email, currentUsecases, filterPolicy)

	// Set the filter policy
	setAttrsInput := &sns.SetSubscriptionAttributesInput{
		SubscriptionArn: aws.String(subscriptionArn),
		AttributeName:   aws.String("FilterPolicy"),
		AttributeValue:  aws.String(filterPolicy),
	}

	_, err = snsClient.SetSubscriptionAttributes(ctx, setAttrsInput)
	if err != nil {
		return fmt.Errorf("failed to set filter policy: %w", err)
	}

	log.Printf("Successfully set filter policy for %s: %s", email, filterPolicy)
	return nil
}

// getUserSubscribedUsecases gets all usecases a user is subscribed to from DynamoDB
func getUserSubscribedUsecases(ctx context.Context, dynamoClient *dynamodb.Client, email string) ([]string, error) {

	// Query for all subscriptions by this user across all usecases
	// We need to scan since we're looking for email across different partition keys
	scanInput := &dynamodb.ScanInput{
		TableName:        aws.String(models.GetTableName()),
		FilterExpression: aws.String("begins_with(pk, :pk_prefix) AND begins_with(sk, :sk_prefix) AND email = :email"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":pk_prefix": &types.AttributeValueMemberS{Value: "USECASE#"},
			":sk_prefix": &types.AttributeValueMemberS{Value: "NOTIFICATION#"},
			":email":     &types.AttributeValueMemberS{Value: email},
		},
	}

	result, err := dynamoClient.Scan(ctx, scanInput)
	if err != nil {
		return nil, err
	}

	var usecaseIds []string
	usecaseSet := make(map[string]bool) // Use set to avoid duplicates

	for _, item := range result.Items {
		if pk, exists := item["pk"]; exists {
			if pkMember, ok := pk.(*types.AttributeValueMemberS); ok {
				pkStr := pkMember.Value
				// Extract usecase ID from "USECASE#{id}"
				if len(pkStr) > 8 && pkStr[:8] == "USECASE#" {
					usecaseId := pkStr[8:]
					if !usecaseSet[usecaseId] {
						usecaseSet[usecaseId] = true
						usecaseIds = append(usecaseIds, usecaseId)
					}
				}
			}
		}
	}

	return usecaseIds, nil
}

// getCurrentFilterPolicyUsecases gets the current usecase_id array from SNS filter policy
func getCurrentFilterPolicyUsecases(ctx context.Context, snsClient *sns.Client, subscriptionArn string) ([]string, error) {
	// Get current subscription attributes
	getAttrsInput := &sns.GetSubscriptionAttributesInput{
		SubscriptionArn: aws.String(subscriptionArn),
	}

	result, err := snsClient.GetSubscriptionAttributes(ctx, getAttrsInput)
	if err != nil {
		return nil, fmt.Errorf("failed to get subscription attributes: %w", err)
	}

	// Check if FilterPolicy exists
	filterPolicyStr, exists := result.Attributes["FilterPolicy"]
	if !exists || filterPolicyStr == "" {
		log.Printf("No existing filter policy found for subscription %s", subscriptionArn)
		return []string{}, nil
	}

	log.Printf("Current filter policy: %s", filterPolicyStr)

	// Parse the filter policy JSON to extract usecase_id array
	var filterPolicy map[string]interface{}
	err = json.Unmarshal([]byte(filterPolicyStr), &filterPolicy)
	if err != nil {
		log.Printf("Error: Could not parse filter policy JSON: %v", err)
		return nil, fmt.Errorf("failed to parse filter policy JSON: %w", err)
	}

	log.Printf("Parsed filter policy: %+v", filterPolicy)

	// Extract usecase_id array
	usecaseIdInterface, exists := filterPolicy["usecase_id"]
	if !exists {
		log.Printf("No usecase_id found in filter policy, keys available: %v", getMapKeys(filterPolicy))
		return []string{}, nil
	}

	log.Printf("Found usecase_id interface: %+v (type: %T)", usecaseIdInterface, usecaseIdInterface)

	// Convert to string array
	var usecases []string
	if usecaseArray, ok := usecaseIdInterface.([]interface{}); ok {
		log.Printf("Successfully cast to []interface{}, length: %d", len(usecaseArray))
		for i, item := range usecaseArray {
			if usecaseStr, ok := item.(string); ok {
				usecases = append(usecases, usecaseStr)
				log.Printf("Added usecase[%d]: %s", i, usecaseStr)
			} else {
				log.Printf("Warning: usecase[%d] is not a string: %+v (type: %T)", i, item, item)
			}
		}
	} else {
		log.Printf("Error: usecase_id is not an array: %+v (type: %T)", usecaseIdInterface, usecaseIdInterface)
	}

	log.Printf("Final parsed usecases: %v", usecases)
	return usecases, nil
}

// getMapKeys returns the keys of a map for debugging
func getMapKeys(m map[string]interface{}) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	return keys
}

// createFilterPolicyJSON creates the SNS filter policy JSON for multiple usecases
func createFilterPolicyJSON(usecaseIds []string) string {
	if len(usecaseIds) == 0 {
		return `{"usecase_id": []}`
	}

	// Build JSON array of usecase IDs
	var jsonParts []string
	for _, id := range usecaseIds {
		jsonParts = append(jsonParts, fmt.Sprintf(`"%s"`, id))
	}

	return fmt.Sprintf(`{"usecase_id": [%s]}`, strings.Join(jsonParts, ","))
}

func main() {
	lambda.Start(handler)
}
