package main

import (
	"context"
	"encoding/json"
	"fmt"
	"lambda/models"
	"log"
	"sort"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

type Step struct {
	PK                 string `json:"pk" dynamodbav:"pk"`
	SK                 string `json:"sk" dynamodbav:"sk"`
	ID                 string `json:"id" dynamodbav:"id"`
	UsecaseId          string `json:"usecaseId" dynamodbav:"usecaseId"`
	Sort               int    `json:"sort" dynamodbav:"sort"`
	Instruction        string `json:"instruction" dynamodbav:"instruction"`
	StepType           string `json:"step_type" dynamodbav:"step_type"`
	SecretKey          string `json:"secret_key,omitempty" dynamodbav:"secret_key,omitempty"`
	ValidationType     string `json:"validation_type,omitempty" dynamodbav:"validation_type,omitempty"`
	ValidationOperator string `json:"validation_operator,omitempty" dynamodbav:"validation_operator,omitempty"`
	ValidationValue    string `json:"validation_value,omitempty" dynamodbav:"validation_value,omitempty"`
	CreatedAt          string `json:"createdAt" dynamodbav:"createdAt"`
	CaptureVariable    string `json:"capture_variable,omitempty" dynamodbav:"capture_variable,omitempty"`
	AssertionVariable  string `json:"assertion_variable,omitempty" dynamodbav:"assertion_variable,omitempty"`
	ValueStep          string `json:"value_step,omitempty" dynamodbav:"value_step,omitempty"`
	ValueType          string `json:"value_type,omitempty" dynamodbav:"value_type,omitempty"`
}

type Response struct {
	Steps []Step `json:"steps"`
}

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	usecaseId := request.PathParameters["id"]
	if usecaseId == "" {
		return events.APIGatewayProxyResponse{StatusCode: 400}, nil
	}

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	client := dynamodb.NewFromConfig(cfg)

	input := &dynamodb.QueryInput{
		TableName:              aws.String(models.GetTableName()),
		KeyConditionExpression: aws.String("pk = :usecaseId AND begins_with(sk, :prefix)"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":usecaseId": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE#%s", usecaseId)},
			":prefix":    &types.AttributeValueMemberS{Value: "STEP#"},
		},
	}

	result, err := client.Query(ctx, input)
	if err != nil {
		log.Printf("Error querying table: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	var steps []Step
	err = attributevalue.UnmarshalListOfMaps(result.Items, &steps)
	if err != nil {
		log.Printf("Error unmarshaling items: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Sort steps by sort field
	sort.Slice(steps, func(i, j int) bool {
		return steps[i].Sort < steps[j].Sort
	})

	response := Response{Steps: steps}
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
