package main

import (
	"context"
	"encoding/json"
	"fmt"
	"lambda/models"
	"log"
	"strings"
	"time"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

type Request struct {
	UsecaseId   string `json:"usecaseId"`
	ExecutionId string `json:"executionId"`
	ActId       string `json:"actId"`
	FileType    string `json:"fileType"` // "html" or "video"
}

type Response struct {
	SignedURL string `json:"signedUrl"`
	FileName  string `json:"fileName"`
}

type Execution struct {
	PK               string `json:"pk" dynamodbav:"pk"`
	SK               string `json:"sk" dynamodbav:"sk"`
	Status           string `json:"status" dynamodbav:"status"`
	StartingURL      string `json:"starting_url" dynamodbav:"starting_url"`
	CreatedAt        string `json:"createdAt" dynamodbav:"created_at"`
	CompletedAt      string `json:"completedAt" dynamodbav:"completed_at"`
	ExecutingAt      string `json:"executingAt" dynamodbav:"executing_at"`
	TriggerType      string `json:"triggerType" dynamodbav:"trigger_type"`
	NovaActSessionID string `json:"novaActSessionId" dynamodbav:"nova_session_id"`
}

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	var req Request

	err := json.Unmarshal([]byte(request.Body), &req)
	if err != nil {
		log.Printf("Error unmarshaling request: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 400}, nil
	}

	log.Printf("UsecaseID: %s, ExecutionID: %s, ActID: %s", req.UsecaseId, req.ExecutionId, req.ActId)

	// Validate required fields
	if req.UsecaseId == "" || req.ExecutionId == "" {
		log.Printf("UsecaseId and ExecutionId are required")
		return events.APIGatewayProxyResponse{StatusCode: 400}, nil
	}

	// ActId is only required for HTML files
	if req.FileType == "html" && req.ActId == "" {
		log.Printf("ActId is required for HTML files")
		return events.APIGatewayProxyResponse{StatusCode: 400}, nil
	}

	// Default to html if fileType is not specified
	if req.FileType == "" {
		req.FileType = "html"
	}

	// Validate fileType
	if req.FileType != "html" && req.FileType != "video" {
		log.Printf("Invalid fileType: %s. Must be 'html' or 'video'", req.FileType)
		return events.APIGatewayProxyResponse{StatusCode: 400}, nil
	}

	// Load AWS config
	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading AWS config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Create DynamoDB client to load execution
	dynamoClient := dynamodb.NewFromConfig(cfg)

	// Load execution to get the Nova Act session ID
	getItemInput := &dynamodb.GetItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE_EXECUTION#%s", req.UsecaseId)},
			"sk": &types.AttributeValueMemberS{Value: fmt.Sprintf("EXECUTION#%s", req.ExecutionId)},
		},
	}

	getItemResult, err := dynamoClient.GetItem(ctx, getItemInput)
	if err != nil {
		log.Printf("Error getting execution from DynamoDB: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	if getItemResult.Item == nil {
		log.Printf("Execution not found: %s/%s", req.UsecaseId, req.ExecutionId)
		return events.APIGatewayProxyResponse{
			StatusCode: 404,
			Headers: map[string]string{
				"Content-Type":                 "application/json",
				"Access-Control-Allow-Origin":  "*",
				"Access-Control-Allow-Methods": "POST, OPTIONS",
				"Access-Control-Allow-Headers": "Content-Type, Authorization",
			},
			Body: `{"error": "Execution not found"}`,
		}, nil
	}

	// Unmarshal execution
	var execution Execution
	err = attributevalue.UnmarshalMap(getItemResult.Item, &execution)
	if err != nil {
		log.Printf("Error unmarshaling execution: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Check if we have a Nova Act session ID
	if execution.NovaActSessionID == "" {
		log.Printf("No Nova Act session ID found for execution: %s", req.ExecutionId)
		return events.APIGatewayProxyResponse{
			StatusCode: 404,
			Headers: map[string]string{
				"Content-Type":                 "application/json",
				"Access-Control-Allow-Origin":  "*",
				"Access-Control-Allow-Methods": "POST, OPTIONS",
				"Access-Control-Allow-Headers": "Content-Type, Authorization",
			},
			Body: `{"error": "Nova Act session not found"}`,
		}, nil
	}

	// Create S3 client
	s3Client := s3.NewFromConfig(cfg)
	bucketName := models.GetBucketName()

	// Use the Nova Act session ID as the prefix
	prefix := execution.NovaActSessionID

	p := fmt.Sprintf("%s/%s/%s/", req.UsecaseId, req.ExecutionId, prefix)

	log.Println("Prefix", p)

	listInput := &s3.ListObjectsV2Input{
		Bucket: aws.String(bucketName),
		Prefix: aws.String(p),
	}

	listResult, err := s3Client.ListObjectsV2(ctx, listInput)
	if err != nil {
		log.Printf("Error listing S3 objects: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Find the file based on type
	var foundKey string
	var fileName string
	var contentType string

	if req.FileType == "html" {
		// Find HTML file matching pattern: act_{act_id}_{wildcard}.html
		for _, obj := range listResult.Contents {
			filePrefix := fmt.Sprintf("%sact_%s_", p, req.ActId)
			log.Println("HTML filePrefix", filePrefix)
			log.Println("obj.Key", *obj.Key)
			if strings.HasPrefix(*obj.Key, filePrefix) && strings.HasSuffix(*obj.Key, ".html") {
				foundKey = *obj.Key
				fileName = strings.TrimPrefix(*obj.Key, p)
				contentType = "text/html"
				log.Printf("Found matching HTML file: %s", foundKey)
				break
			}
		}
	} else if req.FileType == "video" {
		// Find video file matching pattern: {session_id}.mp4
		log.Printf("Looking for video file: %s", ".webm")

		for _, obj := range listResult.Contents {
			log.Println("Checking video obj.Key", *obj.Key)
			if strings.HasSuffix(*obj.Key, ".webm") {
				foundKey = *obj.Key
				fileName = fmt.Sprintf("%s.webm", execution.NovaActSessionID)
				contentType = "video/webm"
				log.Printf("Found matching video file: %s", foundKey)
				break
			}
		}
	}

	if foundKey == "" {
		log.Printf("No %s file found for act_id: %s", req.FileType, req.ActId)
		return events.APIGatewayProxyResponse{
			StatusCode: 404,
			Headers: map[string]string{
				"Content-Type":                 "application/json",
				"Access-Control-Allow-Origin":  "*",
				"Access-Control-Allow-Methods": "POST, OPTIONS",
				"Access-Control-Allow-Headers": "Content-Type, Authorization",
			},
			Body: fmt.Sprintf(`{"error": "%s file not found"}`, req.FileType),
		}, nil
	}

	// Generate pre-signed URL for the found file with appropriate content type
	presignClient := s3.NewPresignClient(s3Client)
	presignResult, err := presignClient.PresignGetObject(ctx, &s3.GetObjectInput{
		Bucket:              aws.String(bucketName),
		Key:                 aws.String(foundKey),
		ResponseContentType: aws.String(contentType),
	}, func(opts *s3.PresignOptions) {
		opts.Expires = time.Duration(3600 * time.Second) // 1 hour expiration
	})

	if err != nil {
		log.Printf("Error generating pre-signed URL: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Prepare response
	response := Response{
		SignedURL: presignResult.URL,
		FileName:  fileName,
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
			"Access-Control-Allow-Methods": "POST, OPTIONS",
			"Access-Control-Allow-Headers": "Content-Type, Authorization",
		},
		Body: string(body),
	}, nil
}

func main() {
	lambda.Start(handler)
}
