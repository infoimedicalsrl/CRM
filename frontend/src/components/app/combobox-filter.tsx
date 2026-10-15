import { useState } from "react";
import { Check, ChevronsUpDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

export interface ComboboxOption {
  value: string;
  label: string;
  hint?: string;
}

export function ComboboxFilter({
  label,
  placeholder,
  searchPlaceholder = "Cerca…",
  options,
  value,
  onChange,
  className,
}: {
  label: string;
  placeholder: string;
  searchPlaceholder?: string;
  options: ComboboxOption[];
  value?: string;
  onChange: (value?: string) => void;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const selected = options.find((option) => option.value === value);

  return (
    <div className={cn("space-y-1.5", className)}>
      <Label className="text-sm font-medium text-foreground">{label}</Label>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            role="combobox"
            aria-expanded={open}
            className="h-11 w-full justify-between bg-background font-normal"
          >
            <span className={cn("truncate", !selected && "text-muted-foreground")}>
              {selected?.label ?? placeholder}
            </span>
            <ChevronsUpDown className="size-4 shrink-0 opacity-50" aria-hidden />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[min(22rem,90vw)] p-0" align="start">
          <Command>
            <CommandInput placeholder={searchPlaceholder} />
            <CommandList>
              <CommandEmpty>Nessun risultato.</CommandEmpty>
              <CommandGroup>
                <CommandItem
                  value="__all__"
                  onSelect={() => {
                    onChange(undefined);
                    setOpen(false);
                  }}
                >
                  <Check className={cn("size-4", value ? "opacity-0" : "opacity-100")} />
                  Tutti
                </CommandItem>
                {options.map((option) => (
                  <CommandItem
                    key={option.value}
                    value={`${option.label} ${option.hint ?? ""} ${option.value}`}
                    onSelect={() => {
                      onChange(option.value);
                      setOpen(false);
                    }}
                  >
                    <Check
                      className={cn(
                        "size-4",
                        value === option.value ? "opacity-100" : "opacity-0",
                      )}
                    />
                    <span className="truncate">{option.label}</span>
                    {option.hint && (
                      <span className="ml-auto truncate font-mono text-xs text-muted-foreground">
                        {option.hint}
                      </span>
                    )}
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  );
}
