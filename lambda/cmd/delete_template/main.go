package main

import (
	"context"
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

	// First, query all items for this template (metadata, steps, variables)
	queryResult, err := client.Query(ctx, &dynamodb.QueryInput{
		TableName:              aws.String(models.GetTableName()),
		KeyConditionExpression: aws.String("pk = :pk"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":pk": &types.AttributeValueMemberS{Value: "TEMPLATE#" + templateID},
		},
	})
	if err != nil {
		log.Printf("Error querying items: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Delete all items in a batch
	if len(queryResult.Items) > 0 {
		var writeRequests []types.WriteRequest
		for _, item := range queryResult.Items {
			writeRequests = append(writeRequests, types.WriteRequest{
				DeleteRequest: &types.DeleteRequest{
					Key: map[string]types.AttributeValue{
						"pk": item["pk"],
						"sk": item["sk"],
					},
				},
			})
		}

		// BatchWriteItem has a limit of 25 items
		for i := 0; i < len(writeRequests); i += 25 {
			end := i + 25
			if end > len(writeRequests) {
				end = len(writeRequests)
			}

			_, err = client.BatchWriteItem(ctx, &dynamodb.BatchWriteItemInput{
				RequestItems: map[string][]types.WriteRequest{
					models.GetTableName(): writeRequests[i:end],
				},
			})
			if err != nil {
				log.Printf("Error batch deleting items: %v", err)
				return events.APIGatewayProxyResponse{StatusCode: 500}, err
			}
		}
	}

	return events.APIGatewayProxyResponse{
		StatusCode: 200,
		Headers: map[string]string{
			"Content-Type":                 "application/json",
			"Access-Control-Allow-Origin":  "*",
			"Access-Control-Allow-Methods": "DELETE, OPTIONS",
			"Access-Control-Allow-Headers": "Content-Type, Authorization",
		},
		Body: `{"message": "Template deleted successfully"}`,
	}, nil
}

func main() {
	lambda.Start(handler)
}
