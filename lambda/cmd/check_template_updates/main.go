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

type StepUpdate struct {
	StepID         string `json:"step_id"`
	CurrentVersion int    `json:"current_version"`
	LatestVersion  int    `json:"latest_version"`
	HasUpdate      bool   `json:"has_update"`
	TemplateID     string `json:"template_id"`
	TemplateStepID string `json:"template_step_id"`
}

type Response struct {
	Updates []StepUpdate `json:"updates"`
}

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	usecaseID := request.PathParameters["id"]
	if usecaseID == "" {
		return events.APIGatewayProxyResponse{StatusCode: 400, Body: "Missing usecase ID"}, nil
	}

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	client := dynamodb.NewFromConfig(cfg)

	// Get all steps for this use case
	stepsResult, err := client.Query(ctx, &dynamodb.QueryInput{
		TableName:              aws.String(models.GetTableName()),
		KeyConditionExpression: aws.String("pk = :pk AND begins_with(sk, :sk)"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":pk": &types.AttributeValueMemberS{Value: "USECASE#" + usecaseID},
			":sk": &types.AttributeValueMemberS{Value: "STEP#"},
		},
	})
	if err != nil {
		log.Printf("Error querying steps: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	var steps []models.Step
	err = attributevalue.UnmarshalListOfMaps(stepsResult.Items, &steps)
	if err != nil {
		log.Printf("Error unmarshaling steps: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	var updates []StepUpdate

	// Check each step that has a template reference
	for _, step := range steps {
		if step.TemplateID == "" {
			continue
		}

		// Get the template metadata to check current version
		templateResult, err := client.GetItem(ctx, &dynamodb.GetItemInput{
			TableName: aws.String(models.GetTableName()),
			Key: map[string]types.AttributeValue{
				"pk": &types.AttributeValueMemberS{Value: "TEMPLATE#" + step.TemplateID},
				"sk": &types.AttributeValueMemberS{Value: "METADATA"},
			},
		})
		if err != nil {
			log.Printf("Error getting template %s: %v", step.TemplateID, err)
			continue
		}

		if templateResult.Item == nil {
			log.Printf("Template %s not found", step.TemplateID)
			continue
		}

		var template models.StepTemplate
		err = attributevalue.UnmarshalMap(templateResult.Item, &template)
		if err != nil {
			log.Printf("Error unmarshaling template: %v", err)
			continue
		}

		// Check if there's an update available
		hasUpdate := template.Version > step.TemplateVersion

		updates = append(updates, StepUpdate{
			StepID:         step.ID,
			CurrentVersion: step.TemplateVersion,
			LatestVersion:  template.Version,
			HasUpdate:      hasUpdate,
			TemplateID:     step.TemplateID,
			TemplateStepID: step.TemplateStepID,
		})
	}

	response := Response{Updates: updates}
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
