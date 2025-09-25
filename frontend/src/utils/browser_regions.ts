export const regionOptions = [
  { label: "us-east-1", value: "us-east-1" },
  { label: "us-west-2", value: "us-west-2" },
  { label: "ap-southeast-2", value: "ap-southeast-2" },
  { label: "eu-central-1", value: "eu-central-1" },
]

export const findRegionOptions = (region: string) => {
  return regionOptions.find(option => option.value === region)
}