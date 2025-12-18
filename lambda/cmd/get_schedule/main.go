package main

import (
	"context"
	"encoding/json"
	"log"
	"os"
	"regexp"
	"strconv"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/scheduler"
	"github.com/aws/aws-sdk-go-v2/service/scheduler/types"
)

func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	usecaseId := request.PathParameters["id"]
	if usecaseId == "" {
		return events.APIGatewayProxyResponse{StatusCode: 400}, nil
	}

	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Printf("Error loading config: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 500}, err
	}

	client := scheduler.NewFromConfig(cfg)

	result, err := client.GetSchedule(ctx, &scheduler.GetScheduleInput{
		Name:      aws.String(usecaseId),
		GroupName: aws.String(os.Getenv("SCHEDULER_GROUP_NAME")),
	})
	if err != nil {
		log.Printf("Error getting schedule: %v", err)
		return events.APIGatewayProxyResponse{StatusCode: 404}, nil
	}

	// Parse rate expression to extract rate and unit
	rateRegex := regexp.MustCompile(`rate\((\d+)\s+(\w+)\)`)
	matches := rateRegex.FindStringSubmatch(*result.ScheduleExpression)

	var rate int
	var unit string
	if len(matches) == 3 {
		rate, _ = strconv.Atoi(matches[1])
		unit = matches[2]
	}

	response, err := json.Marshal(map[string]interface{}{
		"rate":    rate,
		"unit":    unit,
		"enabled": result.State == types.ScheduleStateEnabled,
	})
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
		Body: string(response),
	}, nil
}

func main() {
	lambda.Start(handler)
}
