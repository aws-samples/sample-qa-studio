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
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	templateID := request.PathParameters["id"]
	if templateID == "" {
		return events.APIGatewayProxyResponse{StatusCode: 400, Body: "Missing template ID"}, nil
	}

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	client := dynamodb.NewFromConfig(cfg)

	result, err := client.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: "TEMPLATE#" + templateID},
			"sk": &types.AttributeValueMemberS{Value: "METADATA"},
		},
	})
	if err != nil {
		log.Printf("Error getting item: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	if result.Item == nil {
		return events.APIGatewayProxyResponse{StatusCode: 404, Body: "Template not found"}, nil
	}

	var template models.StepTemplate
	err = attributevalue.UnmarshalMap(result.Item, &template)
	if err != nil {
		log.Printf("Error unmarshaling item: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	response, err := json.Marshal(template)
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
		Body: string(response),
	}, nil
}

func main() {
	lambda.Start(handler)
}
