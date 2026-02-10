/**
 * Simple YAML serializer
 * Converts JavaScript objects to YAML format
 */

function indent(level) {
  return " ".repeat(level * 2)
}

function serializeValue(value, level = 0) {
  if (value === null || value === undefined) {
    return "null"
  }
  
  if (typeof value === "boolean") {
    return value ? "true" : "false"
  }
  
  if (typeof value === "number") {
    return String(value)
  }
  
  if (typeof value === "string") {
    // Check if string needs quoting
    if (value.includes(":") || value.includes("#") || value.startsWith("-") || 
        value.includes("{") || value.includes("}") || value.includes("[") || value.includes("]") ||
        value === "" || value.trim() !== value) {
      return `"${value.replace(/"/g, '\\"')}"`
    }
    return value
  }
  
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return "[]"
    }
    return "\n" + value.map(item => {
      const serialized = serializeValue(item, level + 1)
      if (typeof item === "object" && item !== null && !Array.isArray(item)) {
        // For objects in arrays, render inline or with proper indentation
        const lines = serialized.trim().split("\n")
        return indent(level) + "- " + lines.join("\n" + indent(level) + "  ")
      }
      return indent(level) + "- " + serialized
    }).join("\n")
  }
  
  if (typeof value === "object") {
    const entries = Object.entries(value)
    if (entries.length === 0) {
      return "{}"
    }
    return entries.map(([key, val]) => {
      const serialized = serializeValue(val, level + 1)
      if (typeof val === "object" && val !== null && !Array.isArray(val)) {
        const lines = serialized.trim().split("\n")
        return indent(level) + key + ":" + (lines.length > 0 ? "\n" + lines.join("\n") : "")
      }
      return indent(level) + key + ":" + (serialized.startsWith("\n") ? serialized : " " + serialized)
    }).join("\n")
  }
  
  return String(value)
}

export function toYaml(obj) {
  if (obj === null || obj === undefined) {
    return "null"
  }
  
  if (typeof obj !== "object") {
    return serializeValue(obj)
  }
  
  if (Array.isArray(obj)) {
    if (obj.length === 0) {
      return "[]"
    }
    return obj.map(item => {
      const serialized = serializeValue(item, 0)
      if (typeof item === "object" && item !== null) {
        const lines = serialized.trim().split("\n")
        return "- " + lines.join("\n  ")
      }
      return "- " + serialized
    }).join("\n")
  }
  
  const entries = Object.entries(obj)
  if (entries.length === 0) {
    return "{}"
  }
  
  return entries.map(([key, value]) => {
    const serialized = serializeValue(value, 1)
    if (typeof value === "object" && value !== null && !Array.isArray(value)) {
      const lines = serialized.trim().split("\n")
      return key + ":" + (lines.length > 0 ? "\n" + lines.join("\n") : "")
    }
    return key + ":" + (serialized.startsWith("\n") ? serialized : " " + serialized)
  }).join("\n")
}

export function fromYaml(yaml) {
  // Simple YAML parser - for complex cases, consider using a full YAML library
  // This is a basic implementation for simple structures
  const lines = yaml.split("\n")
  const result = {}
  let current = result
  const stack = []
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const trimmed = line.trim()
    
    if (trimmed === "" || trimmed.startsWith("#")) {
      continue
    }
    
    // Handle array items
    if (trimmed.startsWith("- ")) {
      const value = trimmed.slice(2)
      if (!Array.isArray(current)) {
        // Convert to array if needed
        const parent = stack[stack.length - 1]
        if (parent && typeof parent === "object") {
          const key = Object.keys(parent).find(k => parent[k] === current)
          if (key) {
            parent[key] = [current]
            current = parent[key]
          }
        }
      }
      current.push(parseValue(value))
    }
  }
  
  return result
}

function parseValue(value) {
  value = value.trim()
  
  if (value === "null" || value === "~") {
    return null
  }
  
  if (value === "true") {
    return true
  }
  
  if (value === "false") {
    return false
  }
  
  if (value.startsWith('"') && value.endsWith('"')) {
    return value.slice(1, -1).replace(/\\"/g, '"')
  }
  
  if (value.startsWith("'") && value.endsWith("'")) {
    return value.slice(1, -1)
  }
  
  if (/^-?\d+$/.test(value)) {
    return parseInt(value, 10)
  }
  
  if (/^-?\d+\.\d+$/.test(value)) {
    return parseFloat(value)
  }
  
  return value
}
