package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"sort"
	"strings"
	"time"

	"lambda/models"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/aws/aws-sdk-go-v2/service/secretsmanager"
	secretsmanagerTypes "github.com/aws/aws-sdk-go-v2/service/secretsmanager/types"
)

type ExportData struct {
	ExportVersion string                `json:"exportVersion"`
	ExportedAt    string                `json:"exportedAt"`
	Usecase       UsecaseExport         `json:"usecase"`
	Steps         []StepExport          `json:"steps"`
	Variables     []models.KeyValuePair `json:"variables"`
	Secrets       []SecretExport        `json:"secrets"`
	Hooks         *HooksExport          `json:"hooks,omitempty"`
}

type UsecaseExport struct {
	Name        string   `json:"name"`
	Description string   `json:"description"`
	StartingURL string   `json:"starting_url"`
	Active      bool     `json:"active"`
	Headless    bool     `json:"headless"`
	Region      string   `json:"region"`
	Tags        []string `json:"tags"`
}

type StepExport struct {
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

type SecretExport struct {
	Key         string `json:"key"`
	Description string
	Value       *string `json:"value"` // Always null in export
	Placeholder string  `json:"placeholder"`
}

type HooksExport struct {
	BeforeScript string `json:"beforeScript"`
	AfterScript  string `json:"afterScript"`
}

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	id := request.PathParameters["id"]
	if id == "" {
		return events.APIGatewayProxyResponse{StatusCode: 400}, nil
	}

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	client := dynamodb.NewFromConfig(cfg)
	secretsClient := secretsmanager.NewFromConfig(cfg)

	// Get usecase
	usecaseResult, err := client.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: "USECASES"},
			"sk": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE#%s", id)},
		},
	})
	if err != nil {
		log.Printf("Error getting usecase: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	if usecaseResult.Item == nil {
		return events.APIGatewayProxyResponse{StatusCode: 404}, nil
	}

	var usecase models.UseCase
	err = attributevalue.UnmarshalMap(usecaseResult.Item, &usecase)
	if err != nil {
		log.Printf("Error unmarshaling usecase: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Get steps
	stepsResult, err := client.Query(ctx, &dynamodb.QueryInput{
		TableName:              aws.String(models.GetTableName()),
		KeyConditionExpression: aws.String("pk = :pk AND begins_with(sk, :sk)"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":pk": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE#%s", id)},
			":sk": &types.AttributeValueMemberS{Value: "STEP#"},
		},
	})
	if err != nil {
		log.Printf("Error getting steps: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	steps := make([]StepExport, 0)
	for _, item := range stepsResult.Items {
		var step models.Step
		err = attributevalue.UnmarshalMap(item, &step)
		if err != nil {
			log.Printf("Error unmarshaling step: %v", err)
			continue
		}
		// Convert to clean export format (no IDs)
		stepExport := StepExport{
			Sort:               step.Sort,
			Instruction:        step.Instruction,
			StepType:           step.StepType,
			SecretKey:          step.SecretKey,
			CaptureVariable:    step.CaptureVariable,
			ValidationType:     step.ValidationType,
			ValidationOperator: step.ValidationOperator,
			ValidationValue:    step.ValidationValue,
			AssertionVariable:  step.AssertionVariable,
			ValueStep:          step.ValueStep,
			ValueType:          step.ValueType,
		}
		steps = append(steps, stepExport)
	}

	// Sort steps by Sort property
	sort.Slice(steps, func(i, j int) bool {
		return steps[i].Sort < steps[j].Sort
	})

	// Get variables - initialize as empty slice to avoid null in JSON
	variables := make([]models.KeyValuePair, 0)
	variablesResult, err := client.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE#%s", id)},
			"sk": &types.AttributeValueMemberS{Value: "USECASE_VARIABLES"},
		},
	})
	if err != nil {
		log.Printf("Error getting variables: %v", err)
	} else if variablesResult.Item != nil {
		var usecaseVariables models.UsecaseVariables
		err = attributevalue.UnmarshalMap(variablesResult.Item, &usecaseVariables)
		if err != nil {
			log.Printf("Error unmarshaling variables: %v", err)
		} else {
			variables = usecaseVariables.Variables
			log.Printf("Found %d variables for usecase %s", len(variables), id)
		}
	} else {
		log.Printf("No variables found for usecase %s", id)
	}

	// Get secrets from AWS Secrets Manager (without values) - initialize as empty slice to avoid null in JSON
	secrets := make([]SecretExport, 0)
	secretPrefix := fmt.Sprintf("%s/usecase/%s/", models.GetSecretPrefix(), id)

	// List secrets with the usecase tag (same approach as get_usecase_secrets)
	listSecretsResult, err := secretsClient.ListSecrets(ctx, &secretsmanager.ListSecretsInput{
		Filters: []secretsmanagerTypes.Filter{
			{
				Key:    secretsmanagerTypes.FilterNameStringTypeTagKey,
				Values: []string{"usecase_id"},
			},
			{
				Key:    secretsmanagerTypes.FilterNameStringTypeTagValue,
				Values: []string{id},
			},
		},
	})
	if err != nil {
		log.Printf("Error listing secrets: %v", err)
	} else {
		log.Printf("Found %d secrets for usecase %s", len(listSecretsResult.SecretList), id)
		for _, secret := range listSecretsResult.SecretList {
			if secret.Name != nil && strings.HasPrefix(*secret.Name, secretPrefix) {
				// Extract the secret key from the full name (remove prefix)
				secretKey := strings.TrimPrefix(*secret.Name, secretPrefix)
				description := ""
				if secret.Description != nil {
					description = *secret.Description
				}

				secrets = append(secrets, SecretExport{
					Key:         secretKey,
					Value:       nil, // Never export actual secret values
					Placeholder: fmt.Sprintf("Required: %s", description),
				})
			}
		}
	}

	// Get hooks
	var hooks *HooksExport
	hooksResult, err := client.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE#%s", id)},
			"sk": &types.AttributeValueMemberS{Value: "HOOKS"},
		},
	})
	if err == nil && hooksResult.Item != nil {
		var beforeScript, afterScript string
		if val, ok := hooksResult.Item["before_script"]; ok {
			if s, ok := val.(*types.AttributeValueMemberS); ok {
				beforeScript = s.Value
			}
		}
		if val, ok := hooksResult.Item["after_script"]; ok {
			if s, ok := val.(*types.AttributeValueMemberS); ok {
				afterScript = s.Value
			}
		}
		if beforeScript != "" || afterScript != "" {
			hooks = &HooksExport{
				BeforeScript: beforeScript,
				AfterScript:  afterScript,
			}
		}
	}

	// Convert usecase to clean export format (no IDs or timestamps)
	usecaseExport := UsecaseExport{
		Name:        usecase.Name,
		Description: usecase.Description,
		StartingURL: usecase.StartingURL,
		Active:      usecase.Active,
		Headless:    usecase.Headless,
		Region:      usecase.Region,
		Tags:        usecase.Tags,
	}

	// Create export data
	exportData := ExportData{
		ExportVersion: "1.0",
		ExportedAt:    time.Now().UTC().Format(time.RFC3339),
		Usecase:       usecaseExport,
		Steps:         steps,
		Variables:     variables,
		Secrets:       secrets,
		Hooks:         hooks,
	}

	response, err := json.Marshal(exportData)
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
			"Content-Disposition":          fmt.Sprintf("attachment; filename=\"usecase-%s-export.json\"", id),
		},
		Body: string(response),
	}, nil
}

func main() {
	lambda.Start(handler)
}
