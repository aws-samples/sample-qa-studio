import { enabledRegions, defaultRegion } from "../../../configuration.json"
import { SelectProps } from "@cloudscape-design/components/select";

export const regionOptions = (): SelectProps.Option[] =>  {
  const regions = enabledRegions.map((region:string) => {
    return { label: region, value: region }
  })
  
  return regions
}

export const findRegionOptions = (region: string = defaultRegion) => {
  return regionOptions().find(option => option.value === region)
}