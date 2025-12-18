package main

import (
	"context"
	"fmt"
	"lambda/models"
	"log"
	"time"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	usecaseId := request.PathParameters["id"]
	executionId := request.PathParameters["executionId"]
	fileName := request.PathParameters["fileName"]

	log.Printf("Generating download URL for UsecaseID: %s, ExecutionID: %s, FileName: %s", usecaseId, executionId, fileName)

	// Validate required fields
	if usecaseId == "" || executionId == "" || fileName == "" {
		log.Printf("UsecaseId, ExecutionId, and FileName are required")
		return events.APIGatewayProxyResponse{
			StatusCode: 400,
			Headers: map[string]string{
				"Content-Type":                 "application/json",
				"Access-Control-Allow-Origin":  "*",
				"Access-Control-Allow-Methods": "GET, OPTIONS",
				"Access-Control-Allow-Headers": "Content-Type, Authorization",
			},
			Body: `{"error": "UsecaseId, ExecutionId, and FileName are required"}`,
		}, nil
	}

	// Load AWS config
	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading AWS config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Create S3 client
	s3Client := s3.NewFromConfig(cfg)
	bucketName := models.GetBucketName()

	// Build S3 key
	s3Key := fmt.Sprintf("%s/%s/downloads/%s", usecaseId, executionId, fileName)
	log.Printf("S3 Key: %s", s3Key)

	// Check if file exists
	_, err = s3Client.HeadObject(ctx, &s3.HeadObjectInput{
		Bucket: aws.String(bucketName),
		Key:    aws.String(s3Key),
	})
	if err != nil {
		log.Printf("File not found: %v", err)
		return events.APIGatewayProxyResponse{
			StatusCode: 404,
			Headers: map[string]string{
				"Content-Type":                 "application/json",
				"Access-Control-Allow-Origin":  "*",
				"Access-Control-Allow-Methods": "GET, OPTIONS",
				"Access-Control-Allow-Headers": "Content-Type, Authorization",
			},
			Body: `{"error": "File not found"}`,
		}, nil
	}

	// Generate pre-signed URL
	presignClient := s3.NewPresignClient(s3Client)
	presignResult, err := presignClient.PresignGetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(bucketName),
		Key:    aws.String(s3Key),
	}, func(opts *s3.PresignOptions) {
		opts.Expires = time.Duration(3600 * time.Second) // 1 hour expiration
	})

	if err != nil {
		log.Printf("Error generating pre-signed URL: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	log.Printf("Redirecting to presigned URL: %s", presignResult.URL)

	// Redirect to the presigned URL
	return events.APIGatewayProxyResponse{
		StatusCode: 302,
		Headers: map[string]string{
			"Location":                     presignResult.URL,
			"Access-Control-Allow-Origin":  "*",
			"Access-Control-Allow-Methods": "GET, OPTIONS",
			"Access-Control-Allow-Headers": "Content-Type, Authorization",
		},
	}, nil
}

func main() {
	lambda.Start(handler)
}
