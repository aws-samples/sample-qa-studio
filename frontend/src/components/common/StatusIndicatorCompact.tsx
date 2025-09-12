import Icon, {IconProps} from "@cloudscape-design/components/icon";

export interface StatusIndicatorCompactProps {
  status: "error"|"pending"|"success"
}

export default function StatusIndicatorCompact(props: StatusIndicatorCompactProps) {

  let iconName: IconProps.Name = "status-positive"
  let status: IconProps.Variant = "success"
  
  if (props.status === "pending") {
    iconName = "status-in-progress"
    status = "normal"
  } 
  
  if (props.status === "error") {
    iconName = "status-negative"
    status = "error"
  }

  return (
    <Icon variant={status} name={iconName} />
  )
}