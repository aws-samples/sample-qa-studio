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
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

type UpdateStepRequest struct {
	Instruction        string `json:"instruction"`
	StepType           string `json:"step_type"`
	SecretKey          string `json:"secret_key,omitempty"`
	ValidationType     string `json:"validation_type,omitempty"`
	ValidationOperator string `json:"validation_operator,omitempty"`
	ValidationValue    string `json:"validation_value,omitempty"`
	CaptureVariable    string `json:"capture_variable,omitempty"`
	AssertionVariable  string `json:"assertion_variable,omitempty"`
	ValueType          string `json:"value_type,omitempty"`
}

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	stepId := request.PathParameters["stepId"]
	if stepId == "" {
		return events.APIGatewayProxyResponse{StatusCode: 400}, nil
	}

	id := request.PathParameters["id"]

	var req UpdateStepRequest
	if err := json.Unmarshal([]byte(request.Body), &req); err != nil {
		log.Printf("Error unmarshaling request: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 400}, err
	}

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	client := dynamodb.NewFromConfig(cfg)

	// Build dynamic update expression
	updateExpression := "SET instruction = :instruction, step_type = :step_type"
	expressionAttributeValues := map[string]types.AttributeValue{
		":instruction": &types.AttributeValueMemberS{Value: req.Instruction},
		":step_type":   &types.AttributeValueMemberS{Value: req.StepType},
	}

	// Add secret key if provided
	if req.SecretKey != "" {
		updateExpression += ", secret_key = :secret_key"
		expressionAttributeValues[":secret_key"] = &types.AttributeValueMemberS{Value: req.SecretKey}
	}

	// Add validation fields if provided
	if req.ValidationType != "" {
		updateExpression += ", validation_type = :validation_type"
		expressionAttributeValues[":validation_type"] = &types.AttributeValueMemberS{Value: req.ValidationType}
	}

	if req.ValidationOperator != "" {
		updateExpression += ", validation_operator = :validation_operator"
		expressionAttributeValues[":validation_operator"] = &types.AttributeValueMemberS{Value: req.ValidationOperator}
	}

	if req.ValidationValue != "" {
		updateExpression += ", validation_value = :validation_value"
		expressionAttributeValues[":validation_value"] = &types.AttributeValueMemberS{Value: req.ValidationValue}
	}

	if req.CaptureVariable != "" {
		updateExpression += ", capture_variable = :capture_variable"
		expressionAttributeValues[":capture_variable"] = &types.AttributeValueMemberS{Value: req.CaptureVariable}
	}

	if req.AssertionVariable != "" {
		updateExpression += ", assertion_variable = :assertion_variable"
		expressionAttributeValues[":assertion_variable"] = &types.AttributeValueMemberS{Value: req.AssertionVariable}
	}

	if req.ValueType != "" {
		updateExpression += ", value_type = :value_type"
		expressionAttributeValues[":value_type"] = &types.AttributeValueMemberS{Value: req.ValueType}
	}

	_, err = client.UpdateItem(ctx, &dynamodb.UpdateItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE#%s", id)},
			"sk": &types.AttributeValueMemberS{Value: fmt.Sprintf("STEP#%s", stepId)},
		},
		UpdateExpression:          aws.String(updateExpression),
		ExpressionAttributeValues: expressionAttributeValues,
	})
	if err != nil {
		log.Printf("Error updating step: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	response, err := json.Marshal(map[string]string{
		"status": "step updated",
		"stepId": stepId,
	})
	if err != nil {
		log.Printf("Error marshaling response: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	return events.APIGatewayProxyResponse{
		StatusCode: 200,
		Headers: map[string]string{
			"Content-Type":                 "application/json",
			"Access-Control-Allow-Origin":  "*",
			"Access-Control-Allow-Methods": "PATCH, OPTIONS",
			"Access-Control-Allow-Headers": "Content-Type, Authorization",
		},
		Body: string(response),
	}, nil
}

func main() {
	lambda.Start(handler)
}
