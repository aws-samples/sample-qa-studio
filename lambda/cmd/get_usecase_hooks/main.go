package main

import (
	"context"
	"encoding/json"
	"lambda/models"
	"log"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
)

type UsecaseHooks struct {
	PK           string `json:"pk" dynamodbav:"pk"`
	SK           string `json:"sk" dynamodbav:"sk"`
	BeforeScript string `json:"before_script" dynamodbav:"before_script"`
	AfterScript  string `json:"after_script" dynamodbav:"after_script"`
	CreatedAt    string `json:"createdAt" dynamodbav:"created_at"`
}

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	usecaseId := request.PathParameters["id"]
	if usecaseId == "" {
		return events.APIGatewayProxyResponse{StatusCode: 400}, nil
	}

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	client := dynamodb.NewFromConfig(cfg)

	key, err := attributevalue.MarshalMap(map[string]string{
		"pk": "USECASE#" + usecaseId,
		"sk": "HOOKS",
	})
	if err != nil {
		log.Printf("Error marshaling key: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	result, err := client.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(models.GetTableName()),
		Key:       key,
	})
	if err != nil {
		log.Printf("Error getting item: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	if result.Item == nil {
		return events.APIGatewayProxyResponse{
			StatusCode: 200,
			Headers: map[string]string{
				"Content-Type":                 "application/json",
				"Access-Control-Allow-Origin":  "*",
				"Access-Control-Allow-Methods": "GET, OPTIONS",
				"Access-Control-Allow-Headers": "Content-Type, Authorization",
			},
			Body: `{"before_script":"","after_script":""}`,
		}, nil
	}

	var hooks UsecaseHooks
	err = attributevalue.UnmarshalMap(result.Item, &hooks)
	if err != nil {
		log.Printf("Error unmarshaling item: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	response, err := json.Marshal(hooks)
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
