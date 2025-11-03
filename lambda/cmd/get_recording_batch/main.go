package main

import (
	"compress/gzip"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"lambda/models"
	"log"
	"strconv"
	"strings"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

type Response struct {
	Events     []map[string]interface{} `json:"events"`
	TotalCount int                      `json:"totalCount"`
	TotalPages int                      `json:"totalPages"`
	Page       int                      `json:"page"`
	PageSize   int                      `json:"pageSize"`
	HasMore    bool                     `json:"hasMore"`
}

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (*events.APIGatewayProxyResponse, error) {
	// Get parameters from path
	usecaseId := request.PathParameters["id"]
	executionId := request.PathParameters["executionId"]
	batchId := request.PathParameters["batchId"]

	if usecaseId == "" || executionId == "" || batchId == "" {
		log.Printf("UsecaseId, ExecutionId, and BatchId are required")
		resp := errorResponse(400, "UsecaseId, ExecutionId, and BatchId are required")
		return &resp, nil
	}

	// Validate batchId format (should be 13 digit timestamp)
	if !isValidBatchId(batchId) {
		log.Printf("Invalid batchId format: %s", batchId)
		resp := errorResponse(400, "Invalid batchId format")
		return &resp, nil
	}

	// Parse pagination parameters from query string
	page := 1
	pageSize := 100 // Default page size (reduced to avoid 413 errors)
	if pageStr := request.QueryStringParameters["page"]; pageStr != "" {
		if p, err := strconv.Atoi(pageStr); err == nil && p > 0 {
			page = p
		}
	}
	if pageSizeStr := request.QueryStringParameters["pageSize"]; pageSizeStr != "" {
		if ps, err := strconv.Atoi(pageSizeStr); err == nil && ps > 0 && ps <= 500 {
			pageSize = ps
		}
	}

	log.Printf("Fetching batch %s with pagination: page=%d, pageSize=%d", batchId, page, pageSize)

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

	// Load batch file
	batchKey := fmt.Sprintf("%sbatch_%s.ndjson.gz", recordingPrefix, batchId)
	log.Printf("Loading batch file: %s", batchKey)

	allEvents, err := loadBatchFile(ctx, s3Client, bucketName, batchKey)
	if err != nil {
		log.Printf("Error loading batch file: %v", err)
		resp := errorResponse(404, "Batch file not found")
		return &resp, nil
	}

	totalCount := len(allEvents)
	log.Printf("Loaded %d total events from batch %s", totalCount, batchId)

	// Apply pagination
	startIdx := (page - 1) * pageSize
	endIdx := startIdx + pageSize

	if startIdx >= totalCount {
		startIdx = totalCount
		endIdx = totalCount
	} else if endIdx > totalCount {
		endIdx = totalCount
	}

	paginatedEvents := allEvents[startIdx:endIdx]
	hasMore := endIdx < totalCount
	totalPages := (totalCount + pageSize - 1) / pageSize // Ceiling division

	log.Printf("Returning page %d/%d: events %d-%d of %d (hasMore=%v)", page, totalPages, startIdx, endIdx, totalCount, hasMore)

	// Prepare response
	response := Response{
		Events:     paginatedEvents,
		TotalCount: totalCount,
		TotalPages: totalPages,
		Page:       page,
		PageSize:   pageSize,
		HasMore:    hasMore,
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

func isValidBatchId(batchId string) bool {
	// BatchId should be 13 digit timestamp like "1761741997665"
	if len(batchId) != 13 {
		return false
	}
	for _, c := range batchId {
		if c < '0' || c > '9' {
			return false
		}
	}
	return true
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

func loadBatchFile(ctx context.Context, client *s3.Client, bucket, key string) ([]map[string]interface{}, error) {
	result, err := client.GetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(bucket),
		Key:    aws.String(key),
	})
	if err != nil {
		return nil, err
	}
	defer result.Body.Close()

	// Decompress gzip
	gzReader, err := gzip.NewReader(result.Body)
	if err != nil {
		return nil, fmt.Errorf("error creating gzip reader: %v", err)
	}
	defer gzReader.Close()

	// Read all content
	content, err := io.ReadAll(gzReader)
	if err != nil {
		return nil, fmt.Errorf("error reading content: %v", err)
	}

	// Parse JSON lines
	var batchEvents []map[string]interface{}
	lines := strings.Split(string(content), "\n")
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}

		var event map[string]interface{}
		err := json.Unmarshal([]byte(line), &event)
		if err != nil {
			log.Printf("Error parsing event line: %v", err)
			continue
		}

		// Validate event has required fields
		if _, hasType := event["type"]; !hasType {
			continue
		}
		if _, hasTimestamp := event["timestamp"]; !hasTimestamp {
			continue
		}

		batchEvents = append(batchEvents, event)
	}

	return batchEvents, nil
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
