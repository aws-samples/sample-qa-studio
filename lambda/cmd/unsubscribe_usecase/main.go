package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strings"

	"lambda/models"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/aws/aws-sdk-go-v2/service/sns"
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

	// Find and delete the subscription records for this user and usecase
	queryInput := &dynamodb.QueryInput{
		TableName:              aws.String(models.GetTableName()),
		KeyConditionExpression: aws.String("pk = :pk AND begins_with(sk, :sk)"),
		FilterExpression:       aws.String("email = :email"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":pk":    &types.AttributeValueMemberS{Value: "USECASE#" + usecaseId},
			":sk":    &types.AttributeValueMemberS{Value: "NOTIFICATION#"},
			":email": &types.AttributeValueMemberS{Value: userEmail},
		},
	}

	result, err := dynamoClient.Query(ctx, queryInput)
	if err != nil {
		log.Printf("Error querying subscriptions: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Delete all subscription records for this user and usecase
	for _, item := range result.Items {
		pk := item["pk"].(*types.AttributeValueMemberS).Value
		sk := item["sk"].(*types.AttributeValueMemberS).Value

		_, err = dynamoClient.DeleteItem(ctx, &dynamodb.DeleteItemInput{
			TableName: aws.String(models.GetTableName()),
			Key: map[string]types.AttributeValue{
				"pk": &types.AttributeValueMemberS{Value: pk},
				"sk": &types.AttributeValueMemberS{Value: sk},
			},
		})
		if err != nil {
			log.Printf("Error deleting subscription: %v", err)
			return events.APIGatewayProxyResponse{StatusCode: 500}, err
		}
	}

	log.Printf("Deleted %d DynamoDB records for user %s, usecase %s", len(result.Items), userEmail, usecaseId)

	// Update SNS filter policy to remove this usecase from the user's subscription
	log.Printf("Calling removeUsecaseFromFilterPolicy for user %s, usecase %s", userEmail, usecaseId)
	err = removeUsecaseFromFilterPolicy(ctx, snsClient, userEmail, usecaseId)
	if err != nil {
		log.Printf("Error: Could not update SNS filter policy for %s: %v", userEmail, err)
		// Continue anyway - don't fail the unsubscribe operation
	} else {
		log.Printf("Successfully completed SNS filter policy update for %s", userEmail)
	}

	// Return subscription status (should be false after unsubscribing)
	response := models.SubscriptionStatusResponse{
		IsSubscribed: false,
		Email:        userEmail,
	}

	body, err := json.Marshal(response)
	if err != nil {
		log.Printf("Error marshaling response: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	return events.APIGatewayProxyResponse{
		StatusCode: 200,
		Headers: map[string]string{
			"Content-Type":                 "application/json",
			"Access-Control-Allow-Origin":  "*",
			"Access-Control-Allow-Methods": "DELETE, OPTIONS",
			"Access-Control-Allow-Headers": "Content-Type, Authorization",
		},
		Body: string(body),
	}, nil
}

// removeUsecaseFromFilterPolicy removes a usecase from the user's SNS filter policy
func removeUsecaseFromFilterPolicy(ctx context.Context, snsClient *sns.Client, email, usecaseIdToRemove string) error {
	log.Printf("=== Starting removeUsecaseFromFilterPolicy for email: %s, usecase: %s ===", email, usecaseIdToRemove)

	topicArn := os.Getenv("SNS_TOPIC_ARN")
	if topicArn == "" {
		log.Printf("SNS_TOPIC_ARN not set, skipping SNS filter policy update")
		return nil // Skip if no topic configured
	}

	log.Printf("Using SNS topic ARN: %s", topicArn)

	// Find the user's SNS subscription
	log.Printf("Listing subscriptions for topic: %s", topicArn)
	listInput := &sns.ListSubscriptionsByTopicInput{
		TopicArn: aws.String(topicArn),
	}

	result, err := snsClient.ListSubscriptionsByTopic(ctx, listInput)
	if err != nil {
		log.Printf("Error listing subscriptions: %v", err)
		return fmt.Errorf("failed to list subscriptions: %w", err)
	}

	log.Printf("Found %d total subscriptions", len(result.Subscriptions))

	var subscriptionArn string
	for i, subscription := range result.Subscriptions {
		endpoint := aws.ToString(subscription.Endpoint)
		protocol := aws.ToString(subscription.Protocol)
		arn := aws.ToString(subscription.SubscriptionArn)

		log.Printf("Subscription[%d]: endpoint=%s, protocol=%s, arn=%s", i, endpoint, protocol, arn)

		if endpoint == email && protocol == "email" && arn != "PendingConfirmation" {
			subscriptionArn = arn
			log.Printf("Found matching subscription for %s: %s", email, subscriptionArn)
			break
		}
	}

	if subscriptionArn == "" {
		log.Printf("No confirmed SNS subscription found for %s", email)
		return nil // Not an error - user might not have SNS subscription
	}

	// Get current filter policy from SNS subscription (ONLY source of truth)
	// We ignore DynamoDB state and work purely with what's in the SNS filter policy
	currentUsecases, err := getCurrentFilterPolicyUsecases(ctx, snsClient, subscriptionArn)
	if err != nil {
		log.Printf("Error: Could not get current filter policy: %v", err)
		return fmt.Errorf("failed to get current filter policy: %w", err)
	}

	log.Printf("Current SNS filter policy usecases for %s: %v, removing: %s", email, currentUsecases, usecaseIdToRemove)

	// Check if the usecase is actually in the current filter policy
	usecaseFound := false
	log.Printf("Looking for usecase '%s' (length: %d) in current usecases:", usecaseIdToRemove, len(usecaseIdToRemove))
	for i, id := range currentUsecases {
		log.Printf("  [%d] '%s' (length: %d) - match: %t", i, id, len(id), id == usecaseIdToRemove)
		if id == usecaseIdToRemove {
			usecaseFound = true
			break
		}
	}

	if !usecaseFound {
		log.Printf("ERROR: Usecase '%s' not found in current filter policy %v - nothing to remove", usecaseIdToRemove, currentUsecases)
		log.Printf("This might be a case sensitivity or whitespace issue")
		return nil // Nothing to do
	}

	log.Printf("SUCCESS: Found usecase '%s' in filter policy, proceeding with removal", usecaseIdToRemove)

	// Remove the usecase we're unsubscribing from the current list
	var filteredUsecases []string
	removedCount := 0
	for _, id := range currentUsecases {
		if id != usecaseIdToRemove {
			filteredUsecases = append(filteredUsecases, id)
		} else {
			removedCount++
			log.Printf("Found and removing usecase: %s", id)
		}
	}
	log.Printf("Removed %d instances of usecase %s", removedCount, usecaseIdToRemove)
	log.Printf("Remaining usecases for %s: %v", email, filteredUsecases)

	// If no usecases left, either unsubscribe completely or set empty filter
	if len(filteredUsecases) == 0 {
		log.Printf("User %s has no remaining usecase subscriptions, unsubscribing from SNS", email)
		_, err = snsClient.Unsubscribe(ctx, &sns.UnsubscribeInput{
			SubscriptionArn: aws.String(subscriptionArn),
		})
		if err != nil {
			return fmt.Errorf("failed to unsubscribe from SNS: %w", err)
		}
		log.Printf("Successfully unsubscribed %s from SNS topic", email)
		return nil
	}

	// Update filter policy with remaining usecases
	filterPolicy := createFilterPolicyJSON(filteredUsecases)
	log.Printf("Updating filter policy for %s with remaining usecases %v: %s", email, filteredUsecases, filterPolicy)

	setAttrsInput := &sns.SetSubscriptionAttributesInput{
		SubscriptionArn: aws.String(subscriptionArn),
		AttributeName:   aws.String("FilterPolicy"),
		AttributeValue:  aws.String(filterPolicy),
	}

	log.Printf("About to call SetSubscriptionAttributes with:")
	log.Printf("  SubscriptionArn: %s", subscriptionArn)
	log.Printf("  AttributeName: FilterPolicy")
	log.Printf("  AttributeValue: %s", filterPolicy)

	_, err = snsClient.SetSubscriptionAttributes(ctx, setAttrsInput)
	if err != nil {
		log.Printf("ERROR: SetSubscriptionAttributes failed: %v", err)
		return fmt.Errorf("failed to update filter policy: %w", err)
	}

	log.Printf("SUCCESS: SetSubscriptionAttributes completed successfully")
	log.Printf("Successfully updated filter policy for %s: %s", email, filterPolicy)

	// Verify the update by reading the filter policy again
	log.Printf("Verifying filter policy update...")
	verifyUsecases, verifyErr := getCurrentFilterPolicyUsecases(ctx, snsClient, subscriptionArn)
	if verifyErr != nil {
		log.Printf("Warning: Could not verify filter policy update: %v", verifyErr)
	} else {
		log.Printf("Verified filter policy after update: %v", verifyUsecases)
	}

	return nil
}

// getUserSubscribedUsecases gets all usecases a user is subscribed to from DynamoDB
func getUserSubscribedUsecases(ctx context.Context, dynamoClient *dynamodb.Client, email string) ([]string, error) {
	// Query for all subscriptions by this user across all usecases
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
		// Escape any quotes in the usecase ID
		escapedId := strings.ReplaceAll(id, `"`, `\"`)
		jsonParts = append(jsonParts, fmt.Sprintf(`"%s"`, escapedId))
	}

	return fmt.Sprintf(`{"usecase_id": [%s]}`, strings.Join(jsonParts, ","))
}

func main() {
	lambda.Start(handler)
}
