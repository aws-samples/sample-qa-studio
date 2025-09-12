package main

import (
	"context"
	"encoding/json"
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

type ExecutionStep struct {
	PK                 string `json:"pk" dynamodbav:"pk"`
	SK                 string `json:"sk" dynamodbav:"sk"`
	Sort               int    `json:"sort" dynamodbav:"sort"`
	Instruction        string `json:"instruction" dynamodbav:"instruction"`
	Artefact           string `json:"artefact" dynamodbav:"artefact"`
	Logs               string `json:"logs" dynamodbav:"logs"`
	ActualValue        string `json:"actualValue" dynamodbav:"actual_value,string"`
	ValidationValue    string `json:"validationValue" dynamodbav:"validation_value,string"`
	ValidationOperator string `json:"validationOperator" dynamodbav:"validation_operator,string"`
	ValidationType     string `json:"validationType" dynamodbav:"validation_type,string"`
	CreatedAt          string `json:"createdAt" dynamodbav:"created_at"`
	ActID              string `json:"actId" dynamodbav:"act_id"`
	Status             string `json:"status" dynamodbav:"status"`
	StepType           string `json:"stepType" dynamodbav:"step_type"`
	AssertionVariable  string `json:"assertionVariable" dynamodbav:"assertion_variable"`
}

type Response struct {
	Steps []ExecutionStep `json:"steps"`
}

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	usecaseId := request.PathParameters["id"]
	executionId := request.PathParameters["executionId"]

	log.Printf("usecaseId: %s, executionId: %s", usecaseId, executionId)

	if usecaseId == "" || executionId == "" {
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
		KeyConditionExpression: aws.String("pk = :usecaseExecutionId AND begins_with(sk, :prefix)"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":usecaseExecutionId": &types.AttributeValueMemberS{Value: "EXECUTION#" + executionId},
			":prefix":             &types.AttributeValueMemberS{Value: "EXECUTION_STEP#"},
		},
	}

	result, err := client.Query(ctx, input)
	if err != nil {
		log.Printf("Error querying execution steps: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	var steps []ExecutionStep
	err = attributevalue.UnmarshalListOfMaps(result.Items, &steps)
	if err != nil {
		log.Printf("Error unmarshaling execution steps: %v", err)
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
