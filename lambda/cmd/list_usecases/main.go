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
	UseCases []models.UseCase `json:"usecases"`
}

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	log.Printf("Header: %v", request.Headers)
	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	client := dynamodb.NewFromConfig(cfg)

	input := &dynamodb.QueryInput{
		TableName:              aws.String(models.GetTableName()),
		KeyConditionExpression: aws.String("pk = :prefix AND begins_with(sk, :sortkey)"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":prefix":  &types.AttributeValueMemberS{Value: "USECASES"},
			":sortkey": &types.AttributeValueMemberS{Value: "USECASE#"},
		},
	}

	result, err := client.Query(ctx, input)
	if err != nil {
		log.Printf("Error query table: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	var useCases []models.UseCase
	err = attributevalue.UnmarshalListOfMaps(result.Items, &useCases)
	if err != nil {
		log.Printf("Error unmarshaling items: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	response := Response{UseCases: useCases}
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
