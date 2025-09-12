package main

import (
	"context"
	"encoding/json"
	"fmt"
	"lambda/models"
	"log"
	"sort"
	"strconv"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

type Execution struct {
	PK        string `json:"pk" dynamodbav:"pk"`
	SK        string `json:"sk" dynamodbav:"sk"`
	Status    string `json:"status" dynamodbav:"status"`
	CreatedAt string `json:"createdAt" dynamodbav:"created_at"`
	Triggered string `json:"triggerType" dynamodbav:"trigger_type"`
}

type Response struct {
	Executions []Execution `json:"executions"`
}

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	usecaseId := request.PathParameters["id"]
	if usecaseId == "" {
		return events.APIGatewayProxyResponse{StatusCode: 400}, nil
	}

	limitParameter := request.QueryStringParameters["limit"]
	limit := int32(20)
	if limitParameter != "" {
		if limitParameterConv, err := strconv.ParseInt(limitParameter, 10, 32); err == nil {
			limit = int32(limitParameterConv)
		}
	}

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	client := dynamodb.NewFromConfig(cfg)

	input := &dynamodb.QueryInput{
		TableName:              aws.String(models.GetTableName()),
		Limit:                  aws.Int32(limit),
		ScanIndexForward:       aws.Bool(false),
		KeyConditionExpression: aws.String("pk = :usecaseId AND begins_with(sk, :prefix)"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":usecaseId": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE_EXECUTION#%s", usecaseId)},
			":prefix":    &types.AttributeValueMemberS{Value: "EXECUTION#"},
		},
	}

	result, err := client.Query(ctx, input)
	if err != nil {
		log.Printf("Error querying executions: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	var executions []Execution
	err = attributevalue.UnmarshalListOfMaps(result.Items, &executions)
	if err != nil {
		log.Printf("Error unmarshaling executions: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Sort executions by created_at descending (newest first)
	sort.Slice(executions, func(i, j int) bool {
		return executions[i].CreatedAt > executions[j].CreatedAt
	})

	response := Response{Executions: executions}
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
