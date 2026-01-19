import { SelectProps } from "@cloudscape-design/components/select";

export const regionOptions = (): SelectProps.Option[] =>  {
  const regions = __APP_CONFIG__.enabledRegions.map((region: string) => {
    return { label: region, value: region }
  })
  
  return regions
}

export const findRegionOptions = (region: string = __APP_CONFIG__.defaultRegion) => {
  return regionOptions().find(option => option.value === region)
}