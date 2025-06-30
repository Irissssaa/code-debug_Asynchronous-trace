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

#ifndef GDB_DWARF2_RUST_FUTURE_H
#define GDB_DWARF2_RUST_FUTURE_H

#include "dwarf2/die.h"
#include <string>
#include <vector>
#include <unordered_map>
#include <set>

/* Structure to store Rust Future member information */
struct rust_future_member // Rust Future结构体中的单个成员
{
  /* Member name */
  const char *name;
  
  /* Type ID of the member */
  sect_offset type_id;
  
  /* Whether this member is a state machine */
  bool is_state_machine;
  
  /* Offset of the member in the struct */
  ULONGEST offset;
  
  /* Size of the member */
  ULONGEST size;
};

/* Structure to store Rust Future information */
struct rust_future_info // 一个完整的Rust Future结构体
{
  /* Name of the Future struct */
  const char *name;
  
  /* Whether this is a state machine */
  bool is_state_machine;
  
  /* List of members */
  std::vector<rust_future_member> members;
  
  /* Dependencies on other Futures */
  std::vector<const char *> dependencies;
};

/* Structure to store all Rust Future information */
struct rust_future_collection // 存储所有Rust Future信息
{
  /* Map of struct names to their Future info */
  std::unordered_map<std::string, rust_future_info> futures;
  
  /* Map of type IDs to struct names */
  std::unordered_map<sect_offset, std::string> type_id_to_struct;
};

/* Process all DIEs in a compilation unit to extract Rust Future information */
// 函数声明
void process_rust_futures(struct dwarf2_cu *cu);
void analyze_rust_futures (const char *args, int from_tty);
static void build_future_dependency_tree(struct rust_future_collection *collection);
static void export_future_info_to_json(struct rust_future_collection *collection, const char *filename);
static void resolve_deps_recursive(const struct rust_future_info &future, struct rust_future_collection *collection, std::set<std::string> &seen, std::set<std::string> &deps);
static void parse_rust_future(struct die_info *die, struct rust_future_collection *collection);
static bool is_rust_future(struct die_info *die);
static bool is_state_machine(struct die_info *die);
static void process_rust_futures_on_die(struct die_info *die, struct rust_future_collection *collection);

// 初始化函数
void _initialize_rust_future(void);

#endif /* GDB_DWARF2_RUST_FUTURE_H */ 