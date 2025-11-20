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
	"lambda/utils"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/aws/aws-sdk-go-v2/service/secretsmanager"
	secretsmanagerTypes "github.com/aws/aws-sdk-go-v2/service/secretsmanager/types"
	"github.com/google/uuid"
)

type CloneRequest struct {
	Name string `json:"name"`
}

type CloneResponse struct {
	Success   bool   `json:"success"`
	UsecaseId string `json:"usecaseId"`
	Message   string `json:"message"`
}

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	sourceId := request.PathParameters["id"]
	if sourceId == "" {
		return events.APIGatewayProxyResponse{
			StatusCode: 400,
			Headers: map[string]string{
				"Content-Type":                 "application/json",
				"Access-Control-Allow-Origin":  "*",
				"Access-Control-Allow-Methods": "POST, OPTIONS",
				"Access-Control-Allow-Headers": "Content-Type, Authorization",
			},
			Body: `{"success": false, "message": "Source usecase ID is required"}`,
		}, nil
	}

	var cloneReq CloneRequest
	err := json.Unmarshal([]byte(request.Body), &cloneReq)
	if err != nil {
		log.Printf("Error unmarshaling request: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 400}, err
	}

	if cloneReq.Name == "" {
		return events.APIGatewayProxyResponse{
			StatusCode: 400,
			Headers: map[string]string{
				"Content-Type":                 "application/json",
				"Access-Control-Allow-Origin":  "*",
				"Access-Control-Allow-Methods": "POST, OPTIONS",
				"Access-Control-Allow-Headers": "Content-Type, Authorization",
			},
			Body: `{"success": false, "message": "Name is required"}`,
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

	// Get source usecase
	usecaseResult, err := client.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: "USECASES"},
			"sk": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE#%s", sourceId)},
		},
	})
	if err != nil {
		log.Printf("Error getting source usecase: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	if usecaseResult.Item == nil {
		return events.APIGatewayProxyResponse{
			StatusCode: 404,
			Headers: map[string]string{
				"Content-Type":                 "application/json",
				"Access-Control-Allow-Origin":  "*",
				"Access-Control-Allow-Methods": "POST, OPTIONS",
				"Access-Control-Allow-Headers": "Content-Type, Authorization",
			},
			Body: `{"success": false, "message": "Source usecase not found"}`,
		}, nil
	}

	var sourceUsecase models.UseCase
	err = attributevalue.UnmarshalMap(usecaseResult.Item, &sourceUsecase)
	if err != nil {
		log.Printf("Error unmarshaling source usecase: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	// Generate new usecase ID
	newUsecaseId := uuid.New().String()
	now := time.Now().UTC().Format(time.RFC3339)

	// Create new usecase
	newUsecase := models.UseCase{
		PK:          "USECASES",
		SK:          fmt.Sprintf("USECASE#%s", newUsecaseId),
		ID:          newUsecaseId,
		Name:        cloneReq.Name,
		Description: sourceUsecase.Description,
		StartingURL: sourceUsecase.StartingURL,
		Active:      sourceUsecase.Active,
		Headless:    sourceUsecase.Headless,
		Region:      sourceUsecase.Region,
		Tags:        sourceUsecase.Tags,
		CreatedAt:   now,
	}

	// Save new usecase
	usecaseItem, err := attributevalue.MarshalMap(newUsecase)
	if err != nil {
		log.Printf("Error marshaling new usecase: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	_, err = client.PutItem(ctx, &dynamodb.PutItemInput{
		TableName: aws.String(models.GetTableName()),
		Item:      usecaseItem,
	})
	if err != nil {
		log.Printf("Error saving new usecase: %v", err)
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

	// Clone steps
	stepsResult, err := client.Query(ctx, &dynamodb.QueryInput{
		TableName:              aws.String(models.GetTableName()),
		KeyConditionExpression: aws.String("pk = :pk AND begins_with(sk, :sk)"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":pk": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE#%s", sourceId)},
			":sk": &types.AttributeValueMemberS{Value: "STEP#"},
		},
	})
	if err != nil {
		log.Printf("Error getting source steps: %v", err)
	} else {
		steps := make([]models.Step, 0)
		for _, item := range stepsResult.Items {
			var step models.Step
			err = attributevalue.UnmarshalMap(item, &step)
			if err != nil {
				log.Printf("Error unmarshaling step: %v", err)
				continue
			}
			steps = append(steps, step)
		}

		// Sort steps by Sort property
		sort.Slice(steps, func(i, j int) bool {
			return steps[i].Sort < steps[j].Sort
		})

		// Create new steps
		for _, step := range steps {
			newStepId := uuid.New().String()
			newStep := models.Step{
				PK:                 fmt.Sprintf("USECASE#%s", newUsecaseId),
				SK:                 fmt.Sprintf("STEP#%s", newStepId),
				Sort:               step.Sort,
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
				log.Printf("Error marshaling new step: %v", err)
				continue
			}

			_, err = client.PutItem(ctx, &dynamodb.PutItemInput{
				TableName: aws.String(models.GetTableName()),
				Item:      stepItem,
			})
			if err != nil {
				log.Printf("Error saving new step: %v", err)
			}
		}
	}

	// Clone variables
	variablesResult, err := client.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE#%s", sourceId)},
			"sk": &types.AttributeValueMemberS{Value: "USECASE_VARIABLES"},
		},
	})
	if err == nil && variablesResult.Item != nil {
		var sourceVariables models.UsecaseVariables
		err = attributevalue.UnmarshalMap(variablesResult.Item, &sourceVariables)
		if err == nil && len(sourceVariables.Variables) > 0 {
			newVariables := models.UsecaseVariables{
				PK:        fmt.Sprintf("USECASE#%s", newUsecaseId),
				SK:        "USECASE_VARIABLES",
				Variables: sourceVariables.Variables,
				CreatedAt: now,
			}

			variablesItem, err := attributevalue.MarshalMap(newVariables)
			if err == nil {
				client.PutItem(ctx, &dynamodb.PutItemInput{
					TableName: aws.String(models.GetTableName()),
					Item:      variablesItem,
				})
			}
		}
	}

	// Clone headers
	headersResult, err := client.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE#%s", sourceId)},
			"sk": &types.AttributeValueMemberS{Value: "USECASE_HEADERS"},
		},
	})
	if err == nil && headersResult.Item != nil {
		// Copy headers item with new PK
		newHeadersItem := make(map[string]types.AttributeValue)
		for k, v := range headersResult.Item {
			newHeadersItem[k] = v
		}
		newHeadersItem["pk"] = &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE#%s", newUsecaseId)}
		newHeadersItem["created_at"] = &types.AttributeValueMemberS{Value: now}

		client.PutItem(ctx, &dynamodb.PutItemInput{
			TableName: aws.String(models.GetTableName()),
			Item:      newHeadersItem,
		})
	}

	// Clone secrets (create empty placeholders)
	secretPrefix := fmt.Sprintf("%s/usecase/%s/", models.GetSecretPrefix(), sourceId)
	listSecretsResult, err := secretsClient.ListSecrets(ctx, &secretsmanager.ListSecretsInput{
		Filters: []secretsmanagerTypes.Filter{
			{
				Key:    secretsmanagerTypes.FilterNameStringTypeTagKey,
				Values: []string{"usecase_id"},
			},
			{
				Key:    secretsmanagerTypes.FilterNameStringTypeTagValue,
				Values: []string{sourceId},
			},
		},
	})
	if err == nil {
		for _, secret := range listSecretsResult.SecretList {
			if secret.Name != nil && strings.HasPrefix(*secret.Name, secretPrefix) {
				secretKey := strings.TrimPrefix(*secret.Name, secretPrefix)
				description := ""
				if secret.Description != nil {
					description = *secret.Description
				}

				newSecretName := fmt.Sprintf("%s/usecase/%s/%s", models.GetSecretPrefix(), newUsecaseId, secretKey)

				// Save secret info to DynamoDB
				secretItem := map[string]types.AttributeValue{
					"pk":          &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE#%s", newUsecaseId)},
					"sk":          &types.AttributeValueMemberS{Value: fmt.Sprintf("SECRET#%s", secretKey)},
					"key":         &types.AttributeValueMemberS{Value: secretKey},
					"secret_name": &types.AttributeValueMemberS{Value: newSecretName},
					"description": &types.AttributeValueMemberS{Value: description},
					"created_at":  &types.AttributeValueMemberS{Value: now},
				}

				client.PutItem(ctx, &dynamodb.PutItemInput{
					TableName: aws.String(models.GetTableName()),
					Item:      secretItem,
				})

				// Create empty secret in AWS Secrets Manager
				secretsClient.CreateSecret(ctx, &secretsmanager.CreateSecretInput{
					Name:         aws.String(newSecretName),
					Description:  aws.String(fmt.Sprintf("Cloned secret: %s", description)),
					SecretString: aws.String(""), // Empty value - needs to be configured
					Tags: []secretsmanagerTypes.Tag{
						{
							Key:   aws.String("usecase_id"),
							Value: aws.String(newUsecaseId),
						},
					},
				})
			}
		}
	}

	// Clone hooks
	hooksResult, err := client.GetItem(ctx, &dynamodb.GetItemInput{
		TableName: aws.String(models.GetTableName()),
		Key: map[string]types.AttributeValue{
			"pk": &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE#%s", sourceId)},
			"sk": &types.AttributeValueMemberS{Value: "HOOKS"},
		},
	})
	if err == nil && hooksResult.Item != nil {
		newHooksItem := make(map[string]types.AttributeValue)
		for k, v := range hooksResult.Item {
			newHooksItem[k] = v
		}
		newHooksItem["pk"] = &types.AttributeValueMemberS{Value: fmt.Sprintf("USECASE#%s", newUsecaseId)}
		newHooksItem["created_at"] = &types.AttributeValueMemberS{Value: now}

		client.PutItem(ctx, &dynamodb.PutItemInput{
			TableName: aws.String(models.GetTableName()),
			Item:      newHooksItem,
		})
	}

	// Create response
	response := CloneResponse{
		Success:   true,
		UsecaseId: newUsecaseId,
		Message:   "Usecase cloned successfully",
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
