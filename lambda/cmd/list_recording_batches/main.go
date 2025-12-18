package main

import (
	"context"
	"encoding/json"
	"fmt"
	"lambda/models"
	"log"
	"sort"
	"strings"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

type Response struct {
	Batches  []string               `json:"batches"`
	Metadata map[string]interface{} `json:"metadata"`
}

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (*events.APIGatewayProxyResponse, error) {
	// Get parameters from path
	usecaseId := request.PathParameters["id"]
	executionId := request.PathParameters["executionId"]

	if usecaseId == "" || executionId == "" {
		log.Printf("UsecaseId and ExecutionId are required")
		resp := errorResponse(400, "UsecaseId and ExecutionId are required")
		return &resp, nil
	}

	// Load AWS config
	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading AWS config: %v", err)
		resp := errorResponse(500, "Internal server error")
		return &resp, err
	}

	s3Client := s3.NewFromConfig(cfg)
	bucketName := models.GetBucketName()

	// New structure: /usecaseId/executionId/recording/{unknown_folder_id}/
	recordingBasePrefix := fmt.Sprintf("%s/%s/recording/", usecaseId, executionId)

	log.Printf("Looking for recording folder in: s3://%s/%s", bucketName, recordingBasePrefix)

	// Find the actual recording folder
	recordingPrefix, err := findRecordingFolder(ctx, s3Client, bucketName, recordingBasePrefix)
	if err != nil {
		log.Printf("Error finding recording folder: %v", err)
		resp := errorResponse(404, "Recording folder not found")
		return &resp, nil
	}

	log.Printf("Found recording at: s3://%s/%s", bucketName, recordingPrefix)

	// Load metadata
	metadata, err := loadMetadata(ctx, s3Client, bucketName, recordingPrefix)
	if err != nil {
		log.Printf("Warning: Could not load metadata: %v", err)
		metadata = make(map[string]interface{})
	}

	// List batch files
	batchIds, err := listBatchFiles(ctx, s3Client, bucketName, recordingPrefix)
	if err != nil {
		log.Printf("Error listing batch files: %v", err)
		resp := errorResponse(500, "Failed to list recording batches")
		return &resp, err
	}

	if len(batchIds) == 0 {
		log.Printf("No batch files found in recording folder")
		resp := errorResponse(404, "No recording batches found")
		return &resp, nil
	}

	log.Printf("Found %d batch files", len(batchIds))

	// Prepare response
	response := Response{
		Batches:  batchIds,
		Metadata: metadata,
	}

	body, err := json.Marshal(response)
	if err != nil {
		log.Printf("Error marshaling response: %v", err)
		resp := errorResponse(500, "Internal server error")
		return &resp, err
	}

	return &events.APIGatewayProxyResponse{
		StatusCode: 200,
		Headers: map[string]string{
			"Content-Type":                 "application/json",
			"Access-Control-Allow-Origin":  "*",
			"Access-Control-Allow-Methods": "POST, OPTIONS",
			"Access-Control-Allow-Headers": "Content-Type, Authorization",
		},
		Body: string(body),
	}, nil
}

func findRecordingFolder(ctx context.Context, client *s3.Client, bucket, prefix string) (string, error) {
	listResult, err := client.ListObjectsV2(ctx, &s3.ListObjectsV2Input{
		Bucket:    aws.String(bucket),
		Prefix:    aws.String(prefix),
		Delimiter: aws.String("/"),
		MaxKeys:   aws.Int32(10),
	})
	if err != nil {
		return "", err
	}

	if len(listResult.CommonPrefixes) == 0 {
		return "", fmt.Errorf("no recording folder found under %s", prefix)
	}

	folderPrefix := *listResult.CommonPrefixes[0].Prefix
	log.Printf("Found recording folder: %s", folderPrefix)

	return folderPrefix, nil
}

func loadMetadata(ctx context.Context, client *s3.Client, bucket, prefix string) (map[string]interface{}, error) {
	metadataKey := fmt.Sprintf("%smetadata.json", strings.TrimSuffix(prefix, "/"))

	result, err := client.GetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(bucket),
		Key:    aws.String(metadataKey),
	})
	if err != nil {
		return nil, err
	}
	defer result.Body.Close()

	var metadata map[string]interface{}
	err = json.NewDecoder(result.Body).Decode(&metadata)
	if err != nil {
		return nil, err
	}

	return metadata, nil
}

func listBatchFiles(ctx context.Context, client *s3.Client, bucket, prefix string) ([]string, error) {
	// List all batch files
	listResult, err := client.ListObjectsV2(ctx, &s3.ListObjectsV2Input{
		Bucket: aws.String(bucket),
		Prefix: aws.String(fmt.Sprintf("%sbatch_", prefix)),
	})
	if err != nil {
		return nil, err
	}

	if len(listResult.Contents) == 0 {
		return nil, fmt.Errorf("no batch files found")
	}

	// Extract batch IDs from filenames
	var batchIds []string
	for _, obj := range listResult.Contents {
		key := *obj.Key
		// Extract batch timestamp from "batch_1761741997665.ndjson.gz" -> "1761741997665"
		parts := strings.Split(key, "/")
		filename := parts[len(parts)-1]
		if strings.HasPrefix(filename, "batch_") && strings.HasSuffix(filename, ".gz") {
			batchId := strings.TrimPrefix(filename, "batch_")
			batchId = strings.TrimSuffix(batchId, ".gz")
			// Also remove .ndjson extension if present
			batchId = strings.TrimSuffix(batchId, ".ndjson")
			batchIds = append(batchIds, batchId)
		}
	}

	// Sort batch IDs
	sort.Strings(batchIds)

	return batchIds, nil
}

func errorResponse(statusCode int, message string) events.APIGatewayProxyResponse {
	body, _ := json.Marshal(map[string]string{"error": message})
	return events.APIGatewayProxyResponse{
		StatusCode: statusCode,
		Headers: map[string]string{
			"Content-Type":                 "application/json",
			"Access-Control-Allow-Origin":  "*",
			"Access-Control-Allow-Methods": "POST, OPTIONS",
			"Access-Control-Allow-Headers": "Content-Type, Authorization",
		},
		Body: string(body),
	}
}

func main() {
	lambda.Start(handler)
}
