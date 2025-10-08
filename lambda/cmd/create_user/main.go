package main

import (
	"context"
	"crypto/rand"
	"encoding/json"
	"log"
	"math/big"
	"os"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/cognitoidentityprovider"
	"github.com/aws/aws-sdk-go-v2/service/cognitoidentityprovider/types"
)

type CreateUserRequest struct {
	Email string `json:"email"`
}

type CreateUserResponse struct {
	Username string `json:"username"`
	Email    string `json:"email"`
	Status   string `json:"status"`
}

// generateSecurePassword generates a cryptographically secure random password
func generateSecurePassword(length int) (string, error) {
	const charset = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"
	password := make([]byte, length)

	for i := range password {
		num, err := rand.Int(rand.Reader, big.NewInt(int64(len(charset))))
		if err != nil {
			return "", err
		}
		password[i] = charset[num.Int64()]
	}

	return string(password), nil
}

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	var req CreateUserRequest
	if err := json.Unmarshal([]byte(request.Body), &req); err != nil {
		log.Printf("Error unmarshaling request: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 400}, err
	}

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	client := cognitoidentityprovider.NewFromConfig(cfg)
	userPoolId := os.Getenv("USER_POOL_ID")

	// Generate a secure random password
	temporaryPassword, err := generateSecurePassword(16)
	if err != nil {
		log.Printf("Error generating password: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Create user attributes
	userAttributes := []types.AttributeType{
		{
			Name:  aws.String("email"),
			Value: aws.String(req.Email),
		},
		{
			Name:  aws.String("email_verified"),
			Value: aws.String("false"),
		},
	}

	input := &cognitoidentityprovider.AdminCreateUserInput{
		UserPoolId:        aws.String(userPoolId),
		Username:          aws.String(req.Email),
		UserAttributes:    userAttributes,
		TemporaryPassword: aws.String(temporaryPassword),
		// Don't set MessageAction - this allows Cognito to send the default welcome message
	}

	result, err := client.AdminCreateUser(ctx, input)
	if err != nil {
		log.Printf("Error creating user: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	response := CreateUserResponse{
		Username: aws.ToString(result.User.Username),
		Email:    req.Email,
		Status:   string(result.User.UserStatus),
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
