package main

import (
	"context"
	"encoding/json"
	"fmt"
	"lambda/models"
	"log"
	"os"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	executionId := request.PathParameters["executionId"]
	usecaseId := request.PathParameters["id"]
	if executionId == "" || usecaseId == "" {
		return events.APIGatewayProxyResponse{StatusCode: 400}, nil
	}

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	ddbClient := dynamodb.NewFromConfig(cfg)
	s3Client := s3.NewFromConfig(cfg)

	// Delete S3 objects for this execution
	err = deleteS3Objects(ctx, s3Client, usecaseId, executionId)
	if err != nil {
		log.Printf("Error deleting S3 objects: %v", err)
	}

	// Delete execution
	_, err = ddbClient.DeleteItem(ctx, &dynamodb.DeleteItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: "USECASE_EXECUTION#" + usecaseId},
			"sk": &types.AttributeValueMemberS{Value: "EXECUTION#" + executionId},
		},
	})
	if err != nil {
		log.Printf("Error deleting execution: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Query and delete execution steps
	executionStepsResult, err := ddbClient.Query(ctx, &dynamodb.QueryInput{
		TableName:              aws.String(models.GetTableName()),
		KeyConditionExpression: aws.String("pk = :executionId AND begins_with(sk, :prefix)"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":executionId": &types.AttributeValueMemberS{Value: "EXECUTION#" + executionId},
			":prefix":      &types.AttributeValueMemberS{Value: "EXECUTION_STEP#"},
		},
	})
	if err != nil {
		log.Printf("Error querying execution steps: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	for _, item := range executionStepsResult.Items {
		_, err = ddbClient.DeleteItem(ctx, &dynamodb.DeleteItemInput{
			TableName: aws.String(models.GetTableName()),
			Key: map[string]types.AttributeValue{
				"pk": item["pk"],
				"sk": item["sk"],
			},
		})
		if err != nil {
			log.Printf("Error deleting execution step: %v", err)
		}
	}

	response, err := json.Marshal(map[string]string{
		"status":      "execution deleted",
		"executionId": executionId,
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
			"Access-Control-Allow-Methods": "DELETE, OPTIONS",
			"Access-Control-Allow-Headers": "Content-Type, Authorization",
		},
		Body: string(response),
	}, nil
}

func deleteS3Objects(ctx context.Context, client *s3.Client, usecaseId string, executionId string) error {
	bucketName := os.Getenv("BUCKET_NAME")
	if bucketName == "" {
		return nil // Skip if no bucket configured
	}

	// List objects with execution prefix
	listResult, err := client.ListObjectsV2(ctx, &s3.ListObjectsV2Input{
		Bucket: aws.String(bucketName),
		Prefix: aws.String(fmt.Sprintf("%s/%s/", usecaseId, executionId)),
	})
	if err != nil {
		return err
	}

	// Delete all objects
	for _, obj := range listResult.Contents {
		_, err = client.DeleteObject(ctx, &s3.DeleteObjectInput{
			Bucket: aws.String(bucketName),
			Key:    obj.Key,
		})
		if err != nil {
			log.Printf("Error deleting S3 object %s: %v", *obj.Key, err)
		}
	}

	return nil
}

func main() {
	lambda.Start(handler)
}
