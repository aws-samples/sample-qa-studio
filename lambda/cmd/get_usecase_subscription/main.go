package main

import (
	"context"
	"encoding/json"
	"log"

	"lambda/models"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
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

	client := dynamodb.NewFromConfig(cfg)

	// Query for subscription records for this user and usecase
	queryInput := &dynamodb.QueryInput{
		TableName:              aws.String(models.GetTableName()),
		KeyConditionExpression: aws.String("pk = :pk AND begins_with(sk, :sk)"),
		FilterExpression:       aws.String("email = :email"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":pk":    &types.AttributeValueMemberS{Value: "USECASE#" + usecaseId},
			":sk":    &types.AttributeValueMemberS{Value: "NOTIFICATION#"},
			":email": &types.AttributeValueMemberS{Value: userEmail},
		},
		Limit: aws.Int32(1), // We only need to know if at least one exists
	}

	result, err := client.Query(ctx, queryInput)
	if err != nil {
		log.Printf("Error querying subscriptions: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	response := models.SubscriptionStatusResponse{
		IsSubscribed: len(result.Items) > 0,
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
			"Access-Control-Allow-Methods": "GET, OPTIONS",
			"Access-Control-Allow-Headers": "Content-Type, Authorization",
		},
		Body: string(body),
	}, nil
}

func main() {
	lambda.Start(handler)
}
