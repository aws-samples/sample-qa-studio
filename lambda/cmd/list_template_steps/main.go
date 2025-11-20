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
	Steps []models.TemplateStep `json:"steps"`
}

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

	input := &dynamodb.QueryInput{
		TableName:              aws.String(models.GetTableName()),
		KeyConditionExpression: aws.String("pk = :pk AND begins_with(sk, :sk)"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":pk": &types.AttributeValueMemberS{Value: "TEMPLATE#" + templateID},
			":sk": &types.AttributeValueMemberS{Value: "STEP#"},
		},
	}

	result, err := client.Query(ctx, input)
	if err != nil {
		log.Printf("Error querying table: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	var steps []models.TemplateStep
	err = attributevalue.UnmarshalListOfMaps(result.Items, &steps)
	if err != nil {
		log.Printf("Error unmarshaling items: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	response := Response{Steps: steps}
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
