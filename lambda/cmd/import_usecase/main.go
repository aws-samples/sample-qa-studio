package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"time"

	"lambda/models"
	"lambda/utils"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/aws/aws-sdk-go-v2/service/secretsmanager"
	"github.com/google/uuid"
)

type ImportRequest struct {
	ExportVersion string                `json:"exportVersion"`
	ExportedAt    string                `json:"exportedAt"`
	Usecase       UsecaseImport         `json:"usecase"`
	Steps         []StepImport          `json:"steps"`
	Variables     []models.KeyValuePair `json:"variables"`
	Secrets       []SecretImport        `json:"secrets"`
	Hooks         *HooksImport          `json:"hooks,omitempty"`
}

type UsecaseImport struct {
	Name        string   `json:"name"`
	Description string   `json:"description"`
	StartingURL string   `json:"starting_url"`
	Active      bool     `json:"active"`
	Headless    bool     `json:"headless"`
	Tags        []string `json:"tags"`
}

type StepImport struct {
	Sort               int    `json:"sort"`
	Instruction        string `json:"instruction"`
	StepType           string `json:"step_type"`
	SecretKey          string `json:"secret_key,omitempty"`
	CaptureVariable    string `json:"capture_variable,omitempty"`
	ValidationType     string `json:"validation_type,omitempty"`
	ValidationOperator string `json:"validation_operator,omitempty"`
	ValidationValue    string `json:"validation_value,omitempty"`
	AssertionVariable  string `json:"assertion_variable,omitempty"`
	ValueStep          string `json:"value_step,omitempty"`
	ValueType          string `json:"value_type,omitempty"`
}

type SecretImport struct {
	Key         string  `json:"key"`
	Description string  `json:"description"`
	Value       *string `json:"value"`
	Placeholder string  `json:"placeholder"`
}

type HooksImport struct {
	BeforeScript string `json:"beforeScript"`
	AfterScript  string `json:"afterScript"`
}

type ImportResponse struct {
	Success        bool     `json:"success"`
	UsecaseId      string   `json:"usecaseId"`
	Message        string   `json:"message"`
	MissingSecrets []string `json:"missingSecrets,omitempty"`
}

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	var importReq ImportRequest
	err := json.Unmarshal([]byte(request.Body), &importReq)
	if err != nil {
		log.Printf("Error unmarshaling request: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 400}, err
	}

	// Validate export version
	if importReq.ExportVersion != "1.0" {
		return events.APIGatewayProxyResponse{
			StatusCode: 400,
			Headers: map[string]string{
				"Content-Type":                 "application/json",
				"Access-Control-Allow-Origin":  "*",
				"Access-Control-Allow-Methods": "POST, OPTIONS",
				"Access-Control-Allow-Headers": "Content-Type, Authorization",
			},
			Body: `{"success": false, "message": "Unsupported export version"}`,
		}, nil
	}

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	client := dynamodb.NewFromConfig(cfg)
	secretsClient := secretsmanager.NewFromConfig(cfg)

	// Get user claims for created_by tracking
	claims, err := utils.DecodeClaims(request)
	if err != nil {
		log.Printf("Error getting claims: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 401}, err
	}

	// Generate new IDs
	newUsecaseId := uuid.New().String()
	now := time.Now().UTC().Format(time.RFC3339)

	// Create new usecase with proper pk/sk
	newUsecase := models.UseCase{
		PK:          "USECASES",
		SK:          fmt.Sprintf("USECASE#%s", newUsecaseId),
		ID:          newUsecaseId,
		Name:        importReq.Usecase.Name + " (Imported)",
		Description: importReq.Usecase.Description,
		StartingURL: importReq.Usecase.StartingURL,
		Active:      importReq.Usecase.Active,
		Headless:    importReq.Usecase.Headless,
		Tags:        importReq.Usecase.Tags,
		CreatedAt:   now,
	}

	// Save usecase
	usecaseItem, err := attributevalue.MarshalMap(newUsecase)
	if err != nil {
		log.Printf("Error marshaling usecase: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	_, err = client.PutItem(ctx, &dynamodb.PutItemInput{
		TableName: aws.String(models.GetTableName()),
		Item:      usecaseItem,
	})
	if err != nil {
		log.Printf("Error saving usecase: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Save created_by record
	createdByRecord := models.CreatedByRecord{
		PK:        fmt.Sprintf("USECASE#%s", newUsecaseId),
		SK:        "CREATED_BY",
		Email:     claims.Email,
		Sub:       claims.Sub,
		CreatedAt: now,
	}

	createdByItem, err := attributevalue.MarshalMap(createdByRecord)
	if err == nil {
		client.PutItem(ctx, &dynamodb.PutItemInput{
			TableName: aws.String(models.GetTableName()),
			Item:      createdByItem,
		})
	}

	// Save steps with proper pk/sk recreation
	for i, step := range importReq.Steps {
		newStepId := uuid.New().String()
		newStep := models.Step{
			PK:                 fmt.Sprintf("USECASE#%s", newUsecaseId),
			SK:                 fmt.Sprintf("STEP#%s", newStepId),
			Sort:               i + 1, // Reorder sequentially
			ID:                 newStepId,
			Instruction:        step.Instruction,
			StepType:           step.StepType,
			SecretKey:          step.SecretKey,
			CaptureVariable:    step.CaptureVariable,
			ValidationType:     step.ValidationType,
			ValidationOperator: step.ValidationOperator,
			ValidationValue:    step.ValidationValue,
			AssertionVariable:  step.AssertionVariable,
			CreatedAt:          now,
			ValueStep:          step.ValueStep,
			ValueType:          step.ValueType,
		}

		stepItem, err := attributevalue.MarshalMap(newStep)
		if err != nil {
			log.Printf("Error marshaling step: %v", err)
			continue
		}

		_, err = client.PutItem(ctx, &dynamodb.PutItemInput{
			TableName: aws.String(models.GetTableName()),
			Item:      stepItem,
		})
		if err != nil {
			log.Printf("Error saving step: %v", err)
		}
	}

	// Save variables
	if len(importReq.Variables) > 0 {
		usecaseVariables := models.UsecaseVariables{
			PK:        fmt.Sprintf("USECASE#%s", newUsecaseId),
			SK:        "USECASE_VARIABLES",
			Variables: importReq.Variables,
			CreatedAt: now,
		}

		variablesItem, err := attributevalue.MarshalMap(usecaseVariables)
		if err == nil {
			client.PutItem(ctx, &dynamodb.PutItemInput{
				TableName: aws.String(models.GetTableName()),
				Item:      variablesItem,
			})
		}
	}

	// Save secret placeholders (without values)
	var missingSecrets []string
	for _, secret := range importReq.Secrets {
		secretInfo := models.SecretInfo{
			Key:         secret.Key,
			SecretName:  fmt.Sprintf("%s/%s/%s", models.GetSecretPrefix(), newUsecaseId, secret.Key),
			Description: secret.Description,
			CreatedAt:   now,
		}

		// Save secret info to DynamoDB
		secretItem := map[string]types.AttributeValue{
			"pk":          &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE#%s", newUsecaseId)},
			"sk":          &types.AttributeValueMemberS{Value: fmt.Sprintf("SECRET#%s", secret.Key)},
			"key":         &types.AttributeValueMemberS{Value: secret.Key},
			"secret_name": &types.AttributeValueMemberS{Value: secretInfo.SecretName},
			"description": &types.AttributeValueMemberS{Value: secret.Description},
			"created_at":  &types.AttributeValueMemberS{Value: now},
		}

		_, err = client.PutItem(ctx, &dynamodb.PutItemInput{
			TableName: aws.String(models.GetTableName()),
			Item:      secretItem,
		})
		if err != nil {
			log.Printf("Error saving secret info: %v", err)
		}

		// Create empty secret in AWS Secrets Manager
		_, err = secretsClient.CreateSecret(ctx, &secretsmanager.CreateSecretInput{
			Name:         aws.String(secretInfo.SecretName),
			Description:  aws.String(fmt.Sprintf("Imported secret: %s", secret.Description)),
			SecretString: aws.String(""), // Empty value - needs to be configured
		})
		if err != nil {
			log.Printf("Error creating secret in AWS: %v", err)
		}

		missingSecrets = append(missingSecrets, secret.Key)
	}

	// Save hooks
	if importReq.Hooks != nil {
		hooksItem := map[string]types.AttributeValue{
			"pk":            &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE#%s", newUsecaseId)},
			"sk":            &types.AttributeValueMemberS{Value: "HOOKS"},
			"before_script": &types.AttributeValueMemberS{Value: importReq.Hooks.BeforeScript},
			"after_script":  &types.AttributeValueMemberS{Value: importReq.Hooks.AfterScript},
			"created_at":    &types.AttributeValueMemberS{Value: now},
		}

		_, err = client.PutItem(ctx, &dynamodb.PutItemInput{
			TableName: aws.String(models.GetTableName()),
			Item:      hooksItem,
		})
		if err != nil {
			log.Printf("Error saving hooks: %v", err)
		}
	}

	// Create response
	response := ImportResponse{
		Success:        true,
		UsecaseId:      newUsecaseId,
		Message:        "Usecase imported successfully",
		MissingSecrets: missingSecrets,
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
			"Access-Control-Allow-Methods": "POST, OPTIONS",
			"Access-Control-Allow-Headers": "Content-Type, Authorization",
		},
		Body: string(responseBody),
	}, nil
}

func main() {
	lambda.Start(handler)
}
