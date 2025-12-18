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
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

type ExecutionStep struct {
	PK          string   `json:"pk" dynamodbav:"pk"`
	SK          string   `json:"sk" dynamodbav:"sk"`
	StepID      string   `json:"stepId" dynamodbav:"step_id"`
	Sort        int      `json:"sort" dynamodbav:"sort"`
	Instruction string   `json:"instruction" dynamodbav:"instruction"`
	Artefact    string   `json:"artefact" dynamodbav:"artefact"`
	Logs        []string `json:"logs" dynamodbav:"logs"`
	CreatedAt   string   `json:"createdAt" dynamodbav:"created_at"`
}

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	stepId := request.PathParameters["stepId"]
	executionId := request.PathParameters["executionId"]
	if stepId == "" || executionId == "" {
		return events.APIGatewayProxyResponse{StatusCode: 400}, nil
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
			"pk": &types.AttributeValueMemberS{Value: "EXECUTION_STEP#" + stepId},
			"sk": &types.AttributeValueMemberS{Value: "EXECUTION#" + executionId},
		},
	})
	if err != nil {
		log.Printf("Error getting execution step: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	if result.Item == nil {
		return events.APIGatewayProxyResponse{StatusCode: 404}, nil
	}

	var executionStep ExecutionStep
	err = attributevalue.UnmarshalMap(result.Item, &executionStep)
	if err != nil {
		log.Printf("Error unmarshaling execution step: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	response, err := json.Marshal(executionStep)
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
