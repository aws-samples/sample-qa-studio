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
)

type CreateTemplateVariablesRequest struct {
	Variables []models.KeyValuePair `json:"variables"`
}

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	templateID := request.PathParameters["id"]
	if templateID == "" {
		return events.APIGatewayProxyResponse{StatusCode: 400, Body: "Missing template ID"}, nil
	}

	var req CreateTemplateVariablesRequest
	if err := json.Unmarshal([]byte(request.Body), &req); err != nil {
		log.Printf("Error unmarshaling request: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 400}, err
	}

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	client := dynamodb.NewFromConfig(cfg)

	templateVars := models.TemplateVariables{
		PK:        "TEMPLATE#" + templateID,
		SK:        "VARIABLES",
		Variables: req.Variables,
		CreatedAt: time.Now().UTC().Format(time.RFC3339),
	}

	item, err := attributevalue.MarshalMap(templateVars)
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

	response, err := json.Marshal(templateVars)
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
		Body: string(response),
	}, nil
}

func main() {
	lambda.Start(handler)
}
