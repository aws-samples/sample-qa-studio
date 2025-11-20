package main

import (
	"context"
	"encoding/json"
	"fmt"
	"lambda/models"
	"log"
	"net/http"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

type ReorderTemplateStepsRequest struct {
	StepOrders []StepOrder `json:"step_orders"`
}

type StepOrder struct {
	StepID string `json:"step_id"`
	Sort   int    `json:"sort"`
}

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	log.Printf("Received request: %+v", request)

	templateID := request.PathParameters["id"]
	if templateID == "" {
		return events.APIGatewayProxyResponse{
			StatusCode: http.StatusBadRequest,
			Body:       `{"error": "template ID is required"}`,
		}, nil
	}

	var req ReorderTemplateStepsRequest
	if err := json.Unmarshal([]byte(request.Body), &req); err != nil {
		log.Printf("Error unmarshaling request: %v", err)
		return events.APIGatewayProxyResponse{
			StatusCode: http.StatusBadRequest,
			Body:       `{"error": "Invalid request body"}`,
		}, nil
	}

	if len(req.StepOrders) == 0 {
		return events.APIGatewayProxyResponse{
			StatusCode: http.StatusBadRequest,
			Body:       `{"error": "step_orders is required"}`,
		}, nil
	}

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading AWS config: %v", err)
		return events.APIGatewayProxyResponse{
			StatusCode: http.StatusInternalServerError,
			Body:       `{"error": "Failed to load AWS config"}`,
		}, nil
	}

	dynamoClient := dynamodb.NewFromConfig(cfg)
	tableName := aws.String(models.GetTableName())

	// Use a transaction to update all steps atomically
	var transactItems []types.TransactWriteItem

	for _, stepOrder := range req.StepOrders {
		// Convert sort value to DynamoDB format
		sortValue, err := attributevalue.Marshal(stepOrder.Sort)
		if err != nil {
			log.Printf("Error marshaling sort value: %v", err)
			return events.APIGatewayProxyResponse{
				StatusCode: http.StatusInternalServerError,
				Body:       `{"error": "Failed to marshal sort value"}`,
			}, nil
		}

		transactItem := types.TransactWriteItem{
			Update: &types.Update{
				TableName: tableName,
				Key: map[string]types.AttributeValue{
					"pk": &types.AttributeValueMemberS{Value: fmt.Sprintf("TEMPLATE#%s", templateID)},
					"sk": &types.AttributeValueMemberS{Value: fmt.Sprintf("STEP#%s", stepOrder.StepID)},
				},
				UpdateExpression: aws.String("SET sort = :sort"),
				ExpressionAttributeValues: map[string]types.AttributeValue{
					":sort": sortValue,
				},
			},
		}

		transactItems = append(transactItems, transactItem)
	}

	// Execute the transaction
	_, err = dynamoClient.TransactWriteItems(ctx, &dynamodb.TransactWriteItemsInput{
		TransactItems: transactItems,
	})

	if err != nil {
		log.Printf("Error updating template step orders: %v", err)
		return events.APIGatewayProxyResponse{
			StatusCode: http.StatusInternalServerError,
			Body:       `{"error": "Failed to update template step orders"}`,
		}, nil
	}

	response := map[string]interface{}{
		"message": "Template steps reordered successfully",
		"count":   len(req.StepOrders),
	}

	responseBody, _ := json.Marshal(response)

	return events.APIGatewayProxyResponse{
		StatusCode: http.StatusOK,
		Headers: map[string]string{
			"Content-Type":                 "application/json",
			"Access-Control-Allow-Origin":  "*",
			"Access-Control-Allow-Methods": "PATCH, OPTIONS",
			"Access-Control-Allow-Headers": "Content-Type, Authorization",
		},
		Body: string(responseBody),
	}, nil
}

func main() {
	lambda.Start(handler)
}
