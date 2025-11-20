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
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
)

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	usecaseID := request.PathParameters["id"]
	stepID := request.PathParameters["stepId"]

	if usecaseID == "" || stepID == "" {
		return events.APIGatewayProxyResponse{StatusCode: 400, Body: "Missing usecase ID or step ID"}, nil
	}

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	client := dynamodb.NewFromConfig(cfg)

	// 1. Get the current step
	stepResult, err := client.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: "USECASE#" + usecaseID},
			"sk": &types.AttributeValueMemberS{Value: "STEP#" + stepID},
		},
	})
	if err != nil {
		log.Printf("Error getting step: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	if stepResult.Item == nil {
		return events.APIGatewayProxyResponse{StatusCode: 404, Body: "Step not found"}, nil
	}

	var currentStep models.Step
	err = attributevalue.UnmarshalMap(stepResult.Item, &currentStep)
	if err != nil {
		log.Printf("Error unmarshaling step: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	if currentStep.TemplateID == "" {
		return events.APIGatewayProxyResponse{StatusCode: 400, Body: "Step is not from a template"}, nil
	}

	// 2. Get the template metadata
	templateResult, err := client.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: "TEMPLATE#" + currentStep.TemplateID},
			"sk": &types.AttributeValueMemberS{Value: "METADATA"},
		},
	})
	if err != nil {
		log.Printf("Error getting template: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	if templateResult.Item == nil {
		return events.APIGatewayProxyResponse{StatusCode: 404, Body: "Template not found"}, nil
	}

	var template models.StepTemplate
	err = attributevalue.UnmarshalMap(templateResult.Item, &template)
	if err != nil {
		log.Printf("Error unmarshaling template: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// 3. Get the template step
	templateStepResult, err := client.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: "TEMPLATE#" + currentStep.TemplateID},
			"sk": &types.AttributeValueMemberS{Value: "STEP#" + currentStep.TemplateStepID},
		},
	})
	if err != nil {
		log.Printf("Error getting template step: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	if templateStepResult.Item == nil {
		return events.APIGatewayProxyResponse{StatusCode: 404, Body: "Template step not found"}, nil
	}

	var templateStep models.TemplateStep
	err = attributevalue.UnmarshalMap(templateStepResult.Item, &templateStep)
	if err != nil {
		log.Printf("Error unmarshaling template step: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// 4. Update the step with template data (keep PK, SK, ID, Sort, CreatedAt)
	updatedStep := models.Step{
		PK:        currentStep.PK,
		SK:        currentStep.SK,
		ID:        currentStep.ID,
		Sort:      currentStep.Sort,
		CreatedAt: currentStep.CreatedAt,
		// Update from template
		Instruction:        templateStep.Instruction,
		StepType:           templateStep.StepType,
		SecretKey:          templateStep.SecretKey,
		CaptureVariable:    templateStep.CaptureVariable,
		ValidationType:     templateStep.ValidationType,
		ValidationOperator: templateStep.ValidationOperator,
		ValidationValue:    templateStep.ValidationValue,
		AssertionVariable:  templateStep.AssertionVariable,
		ValueType:          templateStep.ValueType,
		// Update template reference
		TemplateID:      currentStep.TemplateID,
		TemplateStepID:  currentStep.TemplateStepID,
		TemplateVersion: template.Version,
	}

	item, err := attributevalue.MarshalMap(updatedStep)
	if err != nil {
		log.Printf("Error marshaling updated step: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	_, err = client.PutItem(ctx, &dynamodb.PutItemInput{
		TableName: aws.String(models.GetTableName()),
		Item:      item,
	})
	if err != nil {
		log.Printf("Error updating step: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	log.Printf("Updated step %s from template %s (v%d -> v%d)", stepID, currentStep.TemplateID, currentStep.TemplateVersion, template.Version)

	response := map[string]interface{}{
		"message":          "Step updated from template",
		"previous_version": currentStep.TemplateVersion,
		"new_version":      template.Version,
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
