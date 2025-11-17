package main

import (
	"context"
	"encoding/json"
	"fmt"
	"lambda/models"
	"log"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

type Request struct {
	UsecaseId   string `json:"usecaseId"`
	ExecutionId string `json:"executionId"`
}

type FileInfo struct {
	FileName     string `json:"fileName"`
	Size         int64  `json:"size"`
	LastModified string `json:"lastModified"`
}

type Response struct {
	Files []FileInfo `json:"files"`
}

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	usecaseId := request.PathParameters["id"]
	executionId := request.PathParameters["executionId"]

	log.Printf("Listing downloads for UsecaseID: %s, ExecutionID: %s", usecaseId, executionId)

	// Validate required fields
	if usecaseId == "" || executionId == "" {
		log.Printf("UsecaseId and ExecutionId are required")
		return events.APIGatewayProxyResponse{
			StatusCode: 400,
			Headers: map[string]string{
				"Content-Type":                 "application/json",
				"Access-Control-Allow-Origin":  "*",
				"Access-Control-Allow-Methods": "GET, OPTIONS",
				"Access-Control-Allow-Headers": "Content-Type, Authorization",
			},
			Body: `{"error": "UsecaseId and ExecutionId are required"}`,
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

	// List objects in the downloads directory
	prefix := fmt.Sprintf("%s/%s/downloads/", usecaseId, executionId)
	log.Printf("Listing objects with prefix: %s", prefix)

	listInput := &s3.ListObjectsV2Input{
		Bucket: aws.String(bucketName),
		Prefix: aws.String(prefix),
	}

	listResult, err := s3Client.ListObjectsV2(ctx, listInput)
	if err != nil {
		log.Printf("Error listing S3 objects: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Build response with file information
	files := []FileInfo{}
	for _, obj := range listResult.Contents {
		// Extract filename from key (remove prefix)
		fileName := (*obj.Key)[len(prefix):]

		// Skip if it's just the directory marker
		if fileName == "" {
			continue
		}

		files = append(files, FileInfo{
			FileName:     fileName,
			Size:         *obj.Size,
			LastModified: obj.LastModified.Format("2006-01-02T15:04:05Z"),
		})
	}

	log.Printf("Found %d files", len(files))

	// Prepare response
	response := Response{
		Files: files,
	}
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
