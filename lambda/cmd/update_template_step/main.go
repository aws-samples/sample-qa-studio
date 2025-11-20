package main

import (
	"context"
	"encoding/json"
	"log"

	"lambda/models"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/expression"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

type UpdateTemplateStepRequest struct {
	Sort               int    `json:"sort"`
	Instruction        string `json:"instruction"`
	StepType           string `json:"step_type"`
	SecretKey          string `json:"secret_key,omitempty"`
	CaptureVariable    string `json:"capture_variable,omitempty"`
	ValidationType     string `json:"validation_type,omitempty"`
	ValidationOperator string `json:"validation_operator,omitempty"`
	ValidationValue    string `json:"validation_value,omitempty"`
	AssertionVariable  string `json:"assertion_variable,omitempty"`
	ValueType          string `json:"value_type,omitempty"`
}

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	templateID := request.PathParameters["id"]
	stepID := request.PathParameters["stepId"]

	if templateID == "" || stepID == "" {
		return events.APIGatewayProxyResponse{StatusCode: 400, Body: "Missing template ID or step ID"}, nil
	}

	var req UpdateTemplateStepRequest
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

	// Build update expression
	update := expression.Set(expression.Name("sort"), expression.Value(req.Sort)).
		Set(expression.Name("instruction"), expression.Value(req.Instruction)).
		Set(expression.Name("step_type"), expression.Value(req.StepType)).
		Set(expression.Name("secret_key"), expression.Value(req.SecretKey)).
		Set(expression.Name("capture_variable"), expression.Value(req.CaptureVariable)).
		Set(expression.Name("validation_type"), expression.Value(req.ValidationType)).
		Set(expression.Name("validation_operator"), expression.Value(req.ValidationOperator)).
		Set(expression.Name("validation_value"), expression.Value(req.ValidationValue)).
		Set(expression.Name("assertion_variable"), expression.Value(req.AssertionVariable)).
		Set(expression.Name("value_type"), expression.Value(req.ValueType))

	expr, err := expression.NewBuilder().WithUpdate(update).Build()
	if err != nil {
		log.Printf("Error building expression: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	_, err = client.UpdateItem(ctx, &dynamodb.UpdateItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: "TEMPLATE#" + templateID},
			"sk": &types.AttributeValueMemberS{Value: "STEP#" + stepID},
		},
		UpdateExpression:          expr.Update(),
		ExpressionAttributeNames:  expr.Names(),
		ExpressionAttributeValues: expr.Values(),
		ReturnValues:              types.ReturnValueAllNew,
	})
	if err != nil {
		log.Printf("Error updating item: %v", err)
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
		Body: `{"message": "Step updated successfully"}`,
	}, nil
}

func main() {
	lambda.Start(handler)
}
