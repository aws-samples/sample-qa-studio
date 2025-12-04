package main

import (
	"context"
	"encoding/json"
	"log"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/novaact"
)

type ModelResponse struct {
	ModelID     string `json:"modelId"`
	ModelName   string `json:"modelName"`
	IsDefault   bool   `json:"isDefault"`
	Description string `json:"description,omitempty"`
}

type ListModelsResponse struct {
	Models       []ModelResponse `json:"models"`
	DefaultModel string          `json:"defaultModel"`
}

const DEFAULT_MODEL = "nova-act-v1.0"
const NOVA_ACT_REGION = "us-east-1"

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	// Create Nova Act client in us-east-1 (GA region)
	cfg, err := config.LoadDefaultConfig(ctx, config.WithRegion(NOVA_ACT_REGION))
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	novaActClient := novaact.NewFromConfig(cfg)

	// List all available models
	// ClientCompatibilityVersion is required - use 1 for the current version
	listModelsInput := &novaact.ListModelsInput{
		ClientCompatibilityVersion: aws.Int32(1),
	}

	result, err := novaActClient.ListModels(ctx, listModelsInput)
	if err != nil {
		log.Printf("Error listing models: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Convert to response format
	models := make([]ModelResponse, 0)
	for _, model := range result.ModelSummaries {
		modelID := aws.ToString(model.ModelId)

		// Determine lifecycle status
		lifecycleStatus := "available"
		if model.ModelLifecycle != nil && model.ModelLifecycle.Status != "" {
			lifecycleStatus = string(model.ModelLifecycle.Status)
		}

		models = append(models, ModelResponse{
			ModelID:     modelID,
			ModelName:   modelID, // Use modelId as name since ModelName field doesn't exist
			IsDefault:   modelID == DEFAULT_MODEL,
			Description: "Status: " + lifecycleStatus,
		})
	}

	// If no models found or default not in list, add default model
	hasDefault := false
	for _, model := range models {
		if model.ModelID == DEFAULT_MODEL {
			hasDefault = true
			break
		}
	}

	if !hasDefault {
		models = append([]ModelResponse{{
			ModelID:     DEFAULT_MODEL,
			ModelName:   DEFAULT_MODEL,
			IsDefault:   true,
			Description: "Default Nova Act model",
		}}, models...)
	}

	response := ListModelsResponse{
		Models:       models,
		DefaultModel: DEFAULT_MODEL,
	}

	responseBody, err := json.Marshal(response)
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
		Body: string(responseBody),
	}, nil
}

func main() {
	lambda.Start(handler)
}
