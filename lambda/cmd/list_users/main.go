package main

import (
	"context"
	"encoding/json"
	"log"
	"os"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/cognitoidentityprovider"
)

type User struct {
	Username   string            `json:"username"`
	Email      string            `json:"email"`
	Status     string            `json:"status"`
	Enabled    bool              `json:"enabled"`
	CreatedAt  string            `json:"created_at"`
	Attributes map[string]string `json:"attributes"`
}

type Response struct {
	Users []User `json:"users"`
}

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	client := cognitoidentityprovider.NewFromConfig(cfg)
	userPoolId := os.Getenv("USER_POOL_ID")

	input := &cognitoidentityprovider.ListUsersInput{
		UserPoolId: aws.String(userPoolId),
	}

	result, err := client.ListUsers(ctx, input)
	if err != nil {
		log.Printf("Error listing users: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	var users []User
	for _, user := range result.Users {
		userObj := User{
			Username:   aws.ToString(user.Username),
			Status:     string(user.UserStatus),
			Enabled:    user.Enabled,
			CreatedAt:  user.UserCreateDate.Format("2006-01-02T15:04:05Z"),
			Attributes: make(map[string]string),
		}

		for _, attr := range user.Attributes {
			if aws.ToString(attr.Name) == "email" {
				userObj.Email = aws.ToString(attr.Value)
			}
			userObj.Attributes[aws.ToString(attr.Name)] = aws.ToString(attr.Value)
		}

		users = append(users, userObj)
	}

	response := Response{Users: users}
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
