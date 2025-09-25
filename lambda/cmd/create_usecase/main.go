package main

import (
	"context"
	"encoding/json"
	"log"
	"time"

	"lambda/models"
	"lambda/utils"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/google/uuid"
)

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	var req models.CreateUsecaseRequest
	if err := json.Unmarshal([]byte(request.Body), &req); err != nil {
		log.Printf("Error unmarshaling request: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 400}, err
	}

	log.Printf("Request: %v", req)

	// Extract user information from Cognito claims
	claims, err := utils.DecodeClaims(request)
	if err != nil {
		log.Printf("Error unmarshaling request: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 400}, err
	}
	log.Printf("claims: %v", claims)
	email := claims.Email
	sub := claims.Sub

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	client := dynamodb.NewFromConfig(cfg)

	idObject, err := uuid.NewV7()
	if err != nil {
		log.Printf("Error generating UUID: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	id := idObject.String()

	usecase := models.UseCase{
		PK:          "USECASES",
		SK:          "USECASE#" + id,
		ID:          id,
		Name:        req.Name,
		Description: req.Description,
		StartingURL: req.StartingURL,
		Active:      req.Active,
		Headless:    req.Headless,
		Tags:        req.Tags,
		CreatedAt:   time.Now().UTC().Format(time.RFC3339),
		Region:      req.Region,
	}

	item, err := attributevalue.MarshalMap(usecase)
	if err != nil {
		log.Printf("Error marshaling item: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Create CREATED_BY record
	createdByRecord := models.CreatedByRecord{
		PK:        "USECASE#" + id,
		SK:        "CREATED_BY",
		Email:     email,
		Sub:       sub,
		CreatedAt: time.Now().UTC().Format(time.RFC3339),
	}

	createdByItem, err := attributevalue.MarshalMap(createdByRecord)
	if err != nil {
		log.Printf("Error marshaling created by record: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Use TransactWriteItems to ensure both records are created atomically
	_, err = client.TransactWriteItems(ctx, &dynamodb.TransactWriteItemsInput{
		TransactItems: []types.TransactWriteItem{
			{
				Put: &types.Put{
					TableName: aws.String(models.GetTableName()),
					Item:      item,
				},
			},
			{
				Put: &types.Put{
					TableName: aws.String(models.GetTableName()),
					Item:      createdByItem,
				},
			},
		},
	})
	if err != nil {
		log.Printf("Error putting items: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	response, err := json.Marshal(usecase)
	if err != nil {
		log.Printf("Error marshaling response: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	return events.APIGatewayProxyResponse{
		StatusCode: 201,
		Headers: map[string]string{
			"Content-Type":                 "application/json",
			"Access-Control-Allow-Origin":  "*",
			"Access-Control-Allow-Methods": "POST, OPTIONS",
			"Access-Control-Allow-Headers": "Content-Type, Authorization",
		},
		Body: string(response),
	}, nil
}

func main() {
	lambda.Start(handler)
}
