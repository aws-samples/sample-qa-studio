package main

import (
	"context"
	"encoding/json"
	"fmt"
	"lambda/models"
	"log"
	"net/http"
	"strings"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/secretsmanager"
	"github.com/aws/aws-sdk-go-v2/service/secretsmanager/types"
)

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	log.Printf("Received request: %+v", request)

	usecaseID := request.PathParameters["id"]
	if usecaseID == "" {
		return events.APIGatewayProxyResponse{
			StatusCode: http.StatusBadRequest,
			Body:       `{"error": "usecase ID is required"}`,
		}, nil
	}

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading AWS config: %v", err)
		return events.APIGatewayProxyResponse{
			StatusCode: http.StatusInternalServerError,
			Body:       `{"error": "Failed to load AWS config"}`,
		}, nil
	}

	secretsClient := secretsmanager.NewFromConfig(cfg)

	// List secrets with the usecase tag
	listInput := &secretsmanager.ListSecretsInput{
		Filters: []types.Filter{
			{
				Key:    types.FilterNameStringTypeTagKey,
				Values: []string{"usecase_id"},
			},
			{
				Key:    types.FilterNameStringTypeTagValue,
				Values: []string{usecaseID},
			},
		},
	}

	result, err := secretsClient.ListSecrets(ctx, listInput)
	if err != nil {
		log.Printf("Error listing secrets: %v", err)
		return events.APIGatewayProxyResponse{
			StatusCode: http.StatusInternalServerError,
			Body:       `{"error": "Failed to list secrets"}`,
		}, nil
	}

	var secrets []models.SecretInfo
	secretPrefix := fmt.Sprintf("%s/usecase/%s/", models.GetSecretPrefix(), usecaseID)

	for _, secret := range result.SecretList {
		if secret.Name != nil && strings.HasPrefix(*secret.Name, secretPrefix) {
			// Extract the key name from the secret name
			keyName := strings.TrimPrefix(*secret.Name, secretPrefix)

			secretInfo := models.SecretInfo{
				Key:         keyName,
				SecretName:  *secret.Name,
				Description: "",
				CreatedAt:   "",
			}

			if secret.Description != nil {
				secretInfo.Description = *secret.Description
			}

			if secret.CreatedDate != nil {
				secretInfo.CreatedAt = secret.CreatedDate.Format("2006-01-02T15:04:05Z")
			}

			secrets = append(secrets, secretInfo)
		}
	}

	response := models.GetUsecaseSecretsResponse{
		Secrets: secrets,
	}

	responseBody, _ := json.Marshal(response)

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
