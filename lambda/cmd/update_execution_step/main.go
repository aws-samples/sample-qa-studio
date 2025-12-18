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
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

type UpdateExecutionStepRequest struct {
	Artefact string   `json:"artefact"`
	Logs     []string `json:"logs"`
}

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	stepId := request.PathParameters["stepId"]
	executionId := request.PathParameters["executionId"]
	if stepId == "" || executionId == "" {
		return events.APIGatewayProxyResponse{StatusCode: 400}, nil
	}

	var req UpdateExecutionStepRequest
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

	_, err = client.UpdateItem(ctx, &dynamodb.UpdateItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: "EXECUTION_STEP#" + stepId},
			"sk": &types.AttributeValueMemberS{Value: "EXECUTION#" + executionId},
		},
		UpdateExpression: aws.String("SET artefact = :artefact, logs = :logs"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":artefact": &types.AttributeValueMemberS{Value: req.Artefact},
			":logs":     &types.AttributeValueMemberSS{Value: req.Logs},
		},
	})
	if err != nil {
		log.Printf("Error updating execution step: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	response, err := json.Marshal(map[string]string{
		"status": "execution step updated",
		"stepId": stepId,
	})
	if err != nil {
		log.Printf("Error marshaling response: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	return events.APIGatewayProxyResponse{
		StatusCode: 200,
		Headers: map[string]string{
			"Content-Type":                 "application/json",
			"Access-Control-Allow-Origin":  "*",
			"Access-Control-Allow-Methods": "PATCH, OPTIONS",
			"Access-Control-Allow-Headers": "Content-Type, Authorization",
		},
		Body: string(response),
	}, nil
}

func main() {
	lambda.Start(handler)
}
