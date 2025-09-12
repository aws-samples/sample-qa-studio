package main

import (
	"context"
	"encoding/json"
	"fmt"
	"lambda/models"
	"log"
	"net/http"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
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

	var req models.CreateUsecaseSecretsRequest
	if err := json.Unmarshal([]byte(request.Body), &req); err != nil {
		log.Printf("Error unmarshaling request: %v", err)
		return events.APIGatewayProxyResponse{
			StatusCode: http.StatusBadRequest,
			Body:       `{"error": "Invalid request body"}`,
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

	// Create or update secrets
	for _, secret := range req.Secrets {
		secretName := fmt.Sprintf("%s/usecase/%s/%s", models.GetSecretPrefix(), usecaseID, secret.Key)

		// Try to create the secret first
		_, err := secretsClient.CreateSecret(ctx, &secretsmanager.CreateSecretInput{
			Name:         aws.String(secretName),
			SecretString: aws.String(secret.Value),
			Description:  aws.String(fmt.Sprintf("Secret for usecase %s", usecaseID)),
			Tags: []types.Tag{
				{
					Key:   aws.String("usecase_id"),
					Value: aws.String(usecaseID),
				},
				{
					Key:   aws.String("managed_by"),
					Value: aws.String(models.GetSecretPrefix()),
				},
			},
		})

		if err != nil {
			// If secret already exists, update it
			if _, ok := err.(*types.ResourceExistsException); ok {
				_, updateErr := secretsClient.UpdateSecret(ctx, &secretsmanager.UpdateSecretInput{
					SecretId:     aws.String(secretName),
					SecretString: aws.String(secret.Value),
				})
				if updateErr != nil {
					log.Printf("Error updating secret %s: %v", secretName, updateErr)
					return events.APIGatewayProxyResponse{
						StatusCode: http.StatusInternalServerError,
						Body:       fmt.Sprintf(`{"error": "Failed to update secret %s"}`, secret.Key),
					}, nil
				}
			} else {
				log.Printf("Error creating secret %s: %v", secretName, err)
				return events.APIGatewayProxyResponse{
					StatusCode: http.StatusInternalServerError,
					Body:       fmt.Sprintf(`{"error": "Failed to create secret %s"}`, secret.Key),
				}, nil
			}
		}
	}

	response := map[string]interface{}{
		"message": "Secrets created/updated successfully",
		"count":   len(req.Secrets),
	}

	responseBody, _ := json.Marshal(response)

	return events.APIGatewayProxyResponse{
		StatusCode: http.StatusOK,
		Headers: map[string]string{
			"Content-Type":                 "application/json",
			"Access-Control-Allow-Origin":  "*",
			"Access-Control-Allow-Methods": "POST, OPTIONS",
			"Access-Control-Allow-Headers": "Content-Type, Authorization",
		},
		Body: string(responseBody),
	}, nil
}

func main() {
	lambda.Start(handler)
}
