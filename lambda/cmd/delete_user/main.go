package main

import (
	"context"
	"log"
	"net/url"
	"os"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/cognitoidentityprovider"
)

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	encodedUsername := request.PathParameters["username"]
	if encodedUsername == "" {
		log.Printf("Username parameter is required")
		return events.APIGatewayProxyResponse{StatusCode: 400}, nil
	}

	// URL decode the username to handle special characters like @
	username, err := url.QueryUnescape(encodedUsername)
	if err != nil {
		log.Printf("Error decoding username '%s': %v", encodedUsername, err)
		return events.APIGatewayProxyResponse{StatusCode: 400}, nil
	}

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	client := cognitoidentityprovider.NewFromConfig(cfg)
	userPoolId := os.Getenv("USER_POOL_ID")

	input := &cognitoidentityprovider.AdminDeleteUserInput{
		UserPoolId: aws.String(userPoolId),
		Username:   aws.String(username),
	}

	_, err = client.AdminDeleteUser(ctx, input)
	if err != nil {
		log.Printf("Error deleting user with username '%s': %v", username, err)
		return events.APIGatewayProxyResponse{
			StatusCode: 500,
			Headers: map[string]string{
				"Content-Type":                 "application/json",
				"Access-Control-Allow-Origin":  "*",
				"Access-Control-Allow-Methods": "DELETE, OPTIONS",
				"Access-Control-Allow-Headers": "Content-Type, Authorization",
			},
			Body: `{"error": "Failed to delete user"}`,
		}, nil
	}

	return events.APIGatewayProxyResponse{
		StatusCode: 204,
		Headers: map[string]string{
			"Access-Control-Allow-Origin":  "*",
			"Access-Control-Allow-Methods": "DELETE, OPTIONS",
			"Access-Control-Allow-Headers": "Content-Type, Authorization",
		},
	}, nil
}

func main() {
	lambda.Start(handler)
}
