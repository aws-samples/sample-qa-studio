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

type Response struct {
	Templates []models.StepTemplate `json:"templates"`
}

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	client := dynamodb.NewFromConfig(cfg)

	// Query all templates
	input := &dynamodb.ScanInput{
		TableName:        aws.String(models.GetTableName()),
		FilterExpression: aws.String("begins_with(pk, :prefix) AND sk = :sk"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":prefix": &types.AttributeValueMemberS{Value: "TEMPLATE#"},
			":sk":     &types.AttributeValueMemberS{Value: "METADATA"},
		},
	}

	result, err := client.Scan(ctx, input)
	if err != nil {
		log.Printf("Error scanning table: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	var templates []models.StepTemplate
	err = attributevalue.UnmarshalListOfMaps(result.Items, &templates)
	if err != nil {
		log.Printf("Error unmarshaling items: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	response := Response{Templates: templates}
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
