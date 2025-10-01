package main

import (
	"context"
	"encoding/json"
	"log"
	"time"

	"lambda/models"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
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

	client := dynamodb.NewFromConfig(cfg)

	// Create subscription record
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

	_, err = client.PutItem(ctx, &dynamodb.PutItemInput{
		TableName: aws.String(models.GetTableName()),
		Item:      item,
	})
	if err != nil {
		log.Printf("Error putting item: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
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

func main() {
	lambda.Start(handler)
}
