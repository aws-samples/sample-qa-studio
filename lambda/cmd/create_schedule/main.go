package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/scheduler"
	"github.com/aws/aws-sdk-go-v2/service/scheduler/types"
)

type CreateScheduleRequest struct {
	Rate int    `json:"rate"`
	Unit string `json:"unit"`
}

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	usecaseId := request.PathParameters["id"]
	if usecaseId == "" {
		return events.APIGatewayProxyResponse{StatusCode: 400}, nil
	}

	var req CreateScheduleRequest
	if err := json.Unmarshal([]byte(request.Body), &req); err != nil {
		log.Printf("Error unmarshaling request: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 400}, err
	}

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	client := scheduler.NewFromConfig(cfg)

	// Delete existing schedule if it exists
	_, err = client.DeleteSchedule(ctx, &scheduler.DeleteScheduleInput{
		Name:      aws.String(usecaseId),
		GroupName: aws.String(os.Getenv("SCHEDULER_GROUP_NAME")),
	})
	if err != nil {
		log.Printf("No existing schedule to delete or error deleting: %v", err)
	}

	// Create rate expression
	rateExpression := fmt.Sprintf("rate(%d %s)", req.Rate, req.Unit)

	_, err = client.CreateSchedule(ctx, &scheduler.CreateScheduleInput{
		Name:               aws.String(usecaseId),
		GroupName:          aws.String(os.Getenv("SCHEDULER_GROUP_NAME")),
		ScheduleExpression: aws.String(rateExpression),
		Target: &types.Target{
			Arn:     aws.String(os.Getenv("EXECUTE_USECASE_LAMBDA_ARN")),
			RoleArn: aws.String(os.Getenv("SCHEDULER_TARGET_ROLE_ARN")),
			Input:   aws.String(fmt.Sprintf(`{"pathParameters":{"id":"%s"},"queryStringParameters":{"trigger-type":"Scheduled"}}`, usecaseId)),
		},
		FlexibleTimeWindow: &types.FlexibleTimeWindow{
			Mode: "OFF",
		},
	})
	if err != nil {
		log.Printf("Error creating schedule: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	response, err := json.Marshal(map[string]interface{}{
		"status": "schedule created",
		"rate":   req.Rate,
		"unit":   req.Unit,
	})
	if err != nil {
		log.Printf("Error marshaling response: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	return events.APIGatewayProxyResponse{
		StatusCode: 201,
		Headers: map[string]string{
			"Content-Type":                 "application/json",
			"Access-Control-Allow-Origin":  "*",
			"Access-Control-Allow-Methods": "POST, OPTIONS",
			"Access-Control-Allow-Headers": "Content-Type, Authorization",
		},
		Body: string(response),
	}, nil
}

func main() {
	lambda.Start(handler)
}
