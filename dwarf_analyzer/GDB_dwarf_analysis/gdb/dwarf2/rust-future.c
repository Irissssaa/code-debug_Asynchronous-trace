/* Rust Future processing for GDB.

   Copyright (C) 2024 Free Software Foundation, Inc.

   This file is part of GDB.

   This program is free software; you can redistribute it and/or modify
   it under the terms of the GNU General Public License as published by
   the Free Software Foundation; either version 3 of the License, or
   (at your option) any later version.

   This program is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
   GNU General Public License for more details.

   You should have received a copy of the GNU General Public License
   along with this program.  If not, see <http://www.gnu.org/licenses/>.  */

#include "defs.h"
#include "dwarf2/rust-future.h"
#include "dwarf2/die.h"
#include "dwarf2/read.h"
#include "dwarf2/attribute.h"
#include "dwarf2/stringify.h"
#include "complaints.h"
#include "gdbsupport/gdb_obstack.h"
#include "symtab.h"
#include "objfiles.h"
#include "observable.h"
#include "dwarf2/cu.h"
#include "progspace.h"
#include "cli/cli-cmds.h"
#include "cli/cli-decode.h"
#include "top.h"
#include <string>
#include <set>
#include <unordered_map>
#include <vector>
#include <cstring>
#include <ctime>

extern struct cmd_list_element *maintenancelist;

/* Check if a DIE represents a Rust Future */
static bool
is_rust_future (struct die_info *die)
{
  if (die->tag != DW_TAG_structure_type)
    return false;

  struct attribute *name_attr = die->attr (DW_AT_name);
  if (name_attr == NULL)
    return false;

  const char *name = name_attr->as_string ();
  return (strstr (name, "Future") != NULL || 
          strstr (name, "future") != NULL);
}

/* Check if a DIE represents a state machine */
static bool
is_state_machine (struct die_info *die)
{
  if (die->tag != DW_TAG_structure_type)
    return false;

  struct attribute *name_attr = die->attr (DW_AT_name);
  if (name_attr == NULL)
    return false;

  const char *name = name_attr->as_string ();
  return (strstr (name, "State") != NULL || 
          strstr (name, "state") != NULL);
}

/* Parse a Rust Future DIE and its members */
static void
parse_rust_future (struct die_info *die, struct rust_future_collection *collection)
{
  if (!is_rust_future (die))
    return;

  struct attribute *name_attr = die->attr (DW_AT_name);
  if (name_attr == NULL)
    return;

  const char *name = name_attr->as_string ();
  struct rust_future_info future_info;
  future_info.name = name;
  future_info.is_state_machine = is_state_machine (die);
  future_info.members.clear ();
  future_info.dependencies.clear ();

  /* Store type ID mapping */
  collection->type_id_to_struct[die->sect_off] = name;

  /* Parse members */
  struct die_info *child = die->child;
  while (child != NULL)
    {
      if (child->tag == DW_TAG_member)
        {
          struct rust_future_member member;
          struct attribute *member_name = child->attr (DW_AT_name);
          struct attribute *member_type = child->attr (DW_AT_type);
          struct attribute *member_offset = child->attr (DW_AT_data_member_location);
          struct attribute *member_size = child->attr (DW_AT_byte_size);

          if (member_name != NULL && member_type != NULL)
            {
              member.name = member_name->as_string ();
              member.type_id = (sect_offset) member_type->as_unsigned ();
              member.is_state_machine = false;  // Will be updated when processing the type
              member.offset = member_offset ? member_offset->as_unsigned () : 0;
              member.size = member_size ? member_size->as_unsigned () : 0;

              future_info.members.push_back (member);
            }
        }
      child = child->sibling;
    }

  collection->futures[name] = future_info;
}

/* Build dependency tree for Rust Futures */
static void
build_future_dependency_tree (struct rust_future_collection *collection)
{
  for (auto &pair : collection->futures)
    {
      struct rust_future_info &future = pair.second;
      std::set<std::string> seen;
      std::set<std::string> deps;

      /* Start recursive dependency resolution */
      resolve_deps_recursive (future, collection, seen, deps);
      
      /* Convert dependencies to vector */
      future.dependencies.clear();
      for (const auto &dep : deps)
        future.dependencies.push_back(dep.c_str());
    }
}

/* Recursive helper to resolve Future dependencies */
static void
resolve_deps_recursive (const struct rust_future_info &future,
                       struct rust_future_collection *collection,
                       std::set<std::string> &seen,
                       std::set<std::string> &deps)
{
  if (seen.find (future.name) != seen.end ())
    return;

  seen.insert (future.name);

  for (const auto &member : future.members)
    {
      auto it = collection->type_id_to_struct.find (member.type_id);
      if (it == collection->type_id_to_struct.end ())
        continue;

      const std::string &child_name = it->second;
      if (seen.find (child_name) != seen.end ())
        continue;

      auto child_it = collection->futures.find (child_name);
      if (child_it == collection->futures.end ())
        continue;

      const struct rust_future_info &child = child_it->second;
      if (child.is_state_machine)
        deps.insert (child_name);

      resolve_deps_recursive (child, collection, seen, deps);
    }
}

/* Export Rust Future information to JSON */
static void
export_future_info_to_json (struct rust_future_collection *collection,
                           const char *filename)
{
  FILE *fp = fopen (filename, "w");
  if (fp == NULL)
    {
      warning (_("Could not open file %s for writing"), filename);
      return;
    }

  fprintf (fp, "{\n  \"futures\": [\n");
  
  bool first = true;
  for (const auto &pair : collection->futures)
    {
      const struct rust_future_info &future = pair.second;
      
      if (!first)
        fprintf (fp, ",\n");
      first = false;

      fprintf (fp, "    {\n");
      fprintf (fp, "      \"name\": \"%s\",\n", future.name);
      fprintf (fp, "      \"is_state_machine\": %s,\n",
               future.is_state_machine ? "true" : "false");
      
      fprintf (fp, "      \"members\": [\n");
      bool first_member = true;
      for (const auto &member : future.members)
        {
          if (!first_member)
            fprintf (fp, ",\n");
          first_member = false;
          
          fprintf (fp, "        {\n");
          fprintf (fp, "          \"name\": \"%s\",\n", member.name);
          fprintf (fp, "          \"type_id\": \"0x%lx\",\n",
                   (unsigned long) to_underlying (member.type_id));
          fprintf (fp, "          \"is_state_machine\": %s,\n",
                   member.is_state_machine ? "true" : "false");
          fprintf (fp, "          \"offset\": %llu,\n",
                   (unsigned long long) member.offset);
          fprintf (fp, "          \"size\": %llu\n",
                   (unsigned long long) member.size);
          fprintf (fp, "        }");
        }
      fprintf (fp, "\n      ],\n");
      
      fprintf (fp, "      \"dependencies\": [\n");
      bool first_dep = true;
      for (const auto &dep : future.dependencies)
        {
          if (!first_dep)
            fprintf (fp, ",\n");
          first_dep = false;
          fprintf (fp, "        \"%s\"", dep);
        }
      fprintf (fp, "\n      ]\n");
      fprintf (fp, "    }");
    }
  
  fprintf (fp, "\n  ]\n}\n");
  fclose (fp);
}

/* 递归处理所有DIE，收集Rust Future信息 */
static void
process_rust_futures_on_die(struct die_info *die, struct rust_future_collection *collection)
{
  while (die != NULL)
    {
      parse_rust_future(die, collection);
      if (die->child != NULL)
        process_rust_futures_on_die(die->child, collection);
      die = die->sibling;
    }
}

void
process_rust_futures(struct dwarf2_cu *cu)
{
  if (cu == NULL || cu->dies == NULL)
    {
      warning (_("No debug information available for Rust Future analysis"));
      return;
    }

  struct rust_future_collection future_collection;
  future_collection.futures.clear();
  future_collection.type_id_to_struct.clear();

  try
    {
      process_rust_futures_on_die(cu->dies, &future_collection);
      build_future_dependency_tree(&future_collection);
      
      /* Generate timestamp for unique filename */
      time_t now = time(NULL);
      char filename[256];
      snprintf(filename, sizeof(filename), "rust_futures_%ld.json", (long)now);
      
      export_future_info_to_json(&future_collection, filename);
      gdb_printf (_("Rust Future analysis completed. Results saved to %s\n"), filename);
    }
  catch (const std::exception &e)
    {
      warning (_("Error during Rust Future analysis: %s"), e.what());
    }
}

/* Function to analyze Rust Futures in the current program */
void
analyze_rust_futures (const char *args, int from_tty)
{
  int cu_count = 0;
  int analyzed_count = 0;

  for (objfile *objfile : current_program_space->objfiles ())
    {
      if (objfile == nullptr || objfile->sf == nullptr)
        continue;

      dwarf2_per_objfile *per_objfile = get_dwarf2_per_objfile (objfile);
      if (per_objfile == nullptr)
        continue;

      // Aging old units if needed
      per_objfile->age_comp_units();

      // Correctly iterate over all loaded compilation units (CUs)
      for (dwarf2_per_cu_data *per_cu : per_objfile->get_all_per_cus())
        {
          dwarf2_cu *cu = per_objfile->get_cu(per_cu);
          if (cu == nullptr || cu->dies == nullptr)
            continue;
        
          ++cu_count;
        
          try
            {
              process_rust_futures(cu);
              ++analyzed_count;
            }
          catch (const std::exception &e)
            {
              warning(_("Error analyzing CU for Rust Futures: %s"), e.what());
            }
        }
    }

  gdb_printf (_("Rust Future analysis complete.\n"
                       "Total compilation units scanned: %d\n"
                       "Successfully analyzed units: %d\n"),
                     cu_count, analyzed_count);
}

/* Initialize the Rust Future processing */
void
_initialize_rust_future (void)
{
  /* Register a command to manually trigger the analysis */
  add_cmd ("analyze-rust-futures", class_maintenance, analyze_rust_futures,
           _("Analyze Rust Futures in the current program and generate JSON output."),
           &maintenancelist);

  /* Register hook to automatically analyze when program starts */
  gdb::observers::inferior_created.attach ([] (inferior *inf) {
      if (inf != NULL)
        analyze_rust_futures (nullptr, 0);
    }, "rust-future-analyzer");
}