package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

type KeyValuePair struct {
	Key   string `json:"key" dynamodbav:"Key"`
	Value string `json:"value" dynamodbav:"Value"`
}

type ExecutionVariables struct {
	PK               string         `json:"pk" dynamodbav:"pk"`
	SK               string         `json:"sk" dynamodbav:"sk"`
	Variables        []KeyValuePair `json:"variables" dynamodbav:"variables"`
	RuntimeVariables []KeyValuePair `json:"runtime_variables" dynamodbav:"runtime_variables"`
	CreatedAt        string         `json:"created_at" dynamodbav:"created_at"`
}

type Response struct {
	Variables        []KeyValuePair `json:"variables"`
	RuntimeVariables []KeyValuePair `json:"runtime_variables"`
}

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	log.Printf("Request: %+v", request)

	// Extract parameters from path
	executionID := request.PathParameters["executionId"]
	usecaseID := request.PathParameters["id"]

	if executionID == "" || usecaseID == "" {
		return events.APIGatewayProxyResponse{
			StatusCode: http.StatusBadRequest,
			Headers: map[string]string{
				"Content-Type":                 "application/json",
				"Access-Control-Allow-Origin":  "*",
				"Access-Control-Allow-Methods": "GET, OPTIONS",
				"Access-Control-Allow-Headers": "Content-Type, Authorization",
			},
			Body: `{"error": "Missing required parameters"}`,
		}, nil
	}

	// Get table name from environment
	tableName := os.Getenv("TABLE_NAME")
	if tableName == "" {
		log.Printf("TABLE_NAME environment variable not set")
		return events.APIGatewayProxyResponse{
			StatusCode: http.StatusInternalServerError,
			Headers: map[string]string{
				"Content-Type":                 "application/json",
				"Access-Control-Allow-Origin":  "*",
				"Access-Control-Allow-Methods": "GET, OPTIONS",
				"Access-Control-Allow-Headers": "Content-Type, Authorization",
			},
			Body: `{"error": "internal server error"}`,
		}, nil
	}

	// Initialize AWS config
	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading AWS config: %v", err)
		return events.APIGatewayProxyResponse{
			StatusCode: http.StatusInternalServerError,
			Headers: map[string]string{
				"Content-Type":                 "application/json",
				"Access-Control-Allow-Origin":  "*",
				"Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
				"Access-Control-Allow-Headers": "Content-Type, Authorization",
			},
			Body: `{"error": "internal server error"}`,
		}, nil
	}

	// Create DynamoDB client
	dynamoClient := dynamodb.NewFromConfig(cfg)

	// Initialize response with empty arrays
	response := Response{
		Variables:        []KeyValuePair{},
		RuntimeVariables: []KeyValuePair{},
	}

	// Query use case variables (defined variables)
	usecaseResult, err := dynamoClient.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(tableName),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE#%s", usecaseID)},
			"sk": &types.AttributeValueMemberS{Value: "VARIABLES"},
		},
	})

	if err != nil {
		log.Printf("Error querying use case variables: %v", err)
	} else if usecaseResult.Item != nil {
		var usecaseVariables struct {
			Variables []KeyValuePair `json:"variables" dynamodbav:"variables"`
		}
		err = attributevalue.UnmarshalMap(usecaseResult.Item, &usecaseVariables)
		if err != nil {
			log.Printf("Error unmarshaling use case variables: %v", err)
		} else {
			response.Variables = usecaseVariables.Variables
		}
	}

	// Query execution variables (runtime variables)
	executionResult, err := dynamoClient.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(tableName),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: fmt.Sprintf("EXECUTION#%s", executionID)},
			"sk": &types.AttributeValueMemberS{Value: "EXECUTION_VARIABLES"},
		},
	})

	if err != nil {
		log.Printf("Error querying execution variables: %v", err)
	} else if executionResult.Item != nil {
		// Parse the execution variables (runtime variables)
		var executionVariables ExecutionVariables
		err = attributevalue.UnmarshalMap(executionResult.Item, &executionVariables)
		if err != nil {
			log.Printf("Error unmarshaling execution variables: %v", err)
		} else {
			response.RuntimeVariables = executionVariables.RuntimeVariables
		}
	}

	// Convert response to JSON
	responseBody, err := json.Marshal(response)
	if err != nil {
		log.Printf("Error marshaling response: %v", err)
		return events.APIGatewayProxyResponse{
			StatusCode: http.StatusInternalServerError,
			Headers: map[string]string{
				"Content-Type":                 "application/json",
				"Access-Control-Allow-Origin":  "*",
				"Access-Control-Allow-Methods": "GET, OPTIONS",
				"Access-Control-Allow-Headers": "Content-Type, Authorization",
			},
			Body: `{"error": "failed to marshal response"}`,
		}, nil
	}

	log.Printf("Successfully retrieved execution variables for execution %s", executionID)

	return events.APIGatewayProxyResponse{
		StatusCode: http.StatusOK,
		Headers: map[string]string{
			"Content-Type":                 "application/json",
			"Access-Control-Allow-Origin":  "*",
			"Access-Control-Allow-Methods": "GET, OPTIONS",
			"Access-Control-Allow-Headers": "Content-Type, Authorization",
		},
		Body: string(responseBody),
	}, nil
}

func main() {
	lambda.Start(handler)
}
