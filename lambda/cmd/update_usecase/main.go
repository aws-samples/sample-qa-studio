package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"

	"lambda/models"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	usecaseId := request.PathParameters["id"]
	if usecaseId == "" {
		return events.APIGatewayProxyResponse{StatusCode: 400}, nil
	}

	var req models.UpdateUsecaseRequest
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

	// Build update expression and attribute values dynamically
	updateExpr := "SET #name = :name, description = :description, starting_url = :starting_url, active = :active, headless = :headless, execution_region = :execution_region"
	exprAttrNames := map[string]string{
		"#name": "name",
	}
	exprAttrValues := map[string]types.AttributeValue{
		":name":             &types.AttributeValueMemberS{Value: req.Name},
		":description":      &types.AttributeValueMemberS{Value: req.Description},
		":starting_url":     &types.AttributeValueMemberS{Value: req.StartingURL},
		":active":           &types.AttributeValueMemberBOOL{Value: req.Active},
		":headless":         &types.AttributeValueMemberBOOL{Value: req.Headless},
		":execution_region": &types.AttributeValueMemberS{Value: req.Region},
	}

	// Update model_id if provided
	if req.ModelID != "" {
		updateExpr += ", model_id = :model_id"
		exprAttrValues[":model_id"] = &types.AttributeValueMemberS{Value: req.ModelID}
	}

	// Only update tags if provided and not empty (DynamoDB String Sets cannot be empty)
	if len(req.Tags) > 0 {
		updateExpr += ", tags = :tags"
		exprAttrValues[":tags"] = &types.AttributeValueMemberSS{Value: req.Tags}
	}

	_, err = client.UpdateItem(ctx, &dynamodb.UpdateItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: "USECASES"},
			"sk": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE#%s", usecaseId)},
		},
		UpdateExpression:          aws.String(updateExpr),
		ExpressionAttributeNames:  exprAttrNames,
		ExpressionAttributeValues: exprAttrValues,
	})
	if err != nil {
		log.Printf("Error updating usecase: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	response, err := json.Marshal(map[string]string{
		"status":    "usecase updated",
		"usecaseId": usecaseId,
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
